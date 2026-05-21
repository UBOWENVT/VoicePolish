# Centralized Logging for VoicePolish with Loki, Promtail, and Grafana

> Adding production-grade observability to a single-tenant LLM application — and the design choices that make the logs actually useful.

---

## Problem

VoicePolish is a small voice-polishing tool: a user records a clip in the browser, the backend transcribes it (OpenAI Whisper), then a second model (Anthropic Claude) cleans the text up. Two external AI APIs per user request, each with its own latency profile, failure modes, and dollar cost.

Before this change, the only way to see what was happening inside the backend was `docker compose logs backend`. That works for one developer staring at one terminal, but it falls apart the moment you ask any of these questions:

- "What's our LLM error rate over the last hour?"
- "Did latency get worse this week, and from which provider?"
- "Show me every failed call yesterday with its error message."
- "Alert me when error rate goes above 10%."

`grep` and timestamps can answer the first three if you have an afternoon. None of them answer the fourth. Centralized logging gives all four for free, plus the foundation for everything else in observability later (metrics, traces, SLOs).

This document describes the stack added to VoicePolish to answer those questions: **Loki + Promtail + Grafana**, deployed as three additional services in the existing `docker-compose.yml`.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                         Docker host                            │
│                                                                │
│  ┌──────────┐    stdout      ┌──────────┐                      │
│  │ backend  │ ─────────────> │ Docker   │                      │
│  │ (FastAPI)│   JSON lines    │ daemon   │                     │
│  └──────────┘                 └────┬─────┘                     │
│       ▲                            │                            │
│       │ HTTP                       │ /var/run/docker.sock      │
│       │                            ▼                            │
│  ┌────┴─────┐               ┌──────────┐                       │
│  │  nginx   │               │ Promtail │                       │
│  └──────────┘               │ (sidecar)│                       │
│       ▲                     └────┬─────┘                       │
│       │ :8080                    │ push                         │
│  user browser                    ▼                              │
│                              ┌──────────┐    query             │
│                              │   Loki   │ <─────┐               │
│                              └──────────┘       │               │
│                                                 │               │
│                                            ┌────┴─────┐         │
│                                            │ Grafana  │ :3000   │
│                                            └──────────┘ <── user│
└────────────────────────────────────────────────────────────────┘
```

Each component does exactly one job:

- **Promtail** discovers running containers through the Docker socket and tails their stdout. It attaches labels (`compose_service`, `container`, `stream`) so queries can scope to a single app cleanly. No per-service config; new containers are picked up automatically.
- **Loki** stores log lines plus their labels. Unlike Elasticsearch, Loki indexes only the labels, not the log body — which makes it about an order of magnitude cheaper to run, at the cost of slower full-text search. Fine for the lab; fine for most apps.
- **Grafana** queries Loki, draws dashboards, and fires alerts. It does not store data itself; if the volume gets nuked, dashboards are restored from provisioning config.

---

## Structured logging — the part that matters

Centralized logging is only as useful as the logs you feed it. A pile of free-form English sentences is hard to aggregate; a stream of single-line JSON events is trivial.

VoicePolish's two external API calls (Whisper and Claude) now emit a uniform event:

```json
{
  "timestamp": "2026-05-21T14:32:08",
  "logger": "app.services.polish_service",
  "level": "INFO",
  "message": "ai_api.call",
  "event": "ai_api.call",
  "provider_type": "llm",
  "provider": "anthropic",
  "model": "claude-haiku-4-5-20251001",
  "mode": "clean",
  "status": "success",
  "duration_ms": 919,
  "input_tokens": 89,
  "output_tokens": 37,
  "output_chars": 137
}
```

A few choices worth flagging:

- **`event="ai_api.call"`, not `"llm.call"`** — Whisper is a speech-to-text model, not strictly an LLM. Lumping both under `ai_api.call` and adding a `provider_type` field (`llm` vs `speech_to_text`) keeps room for image generation, embeddings, or anything else the same shape.
- **Same schema for success and failure** — failures add `error_type` and a truncated `error_message`; everything else is identical. One LogQL query can compute error rate; another can chart latency on success only.
- **No payloads in logs** — we record the size of the audio in bytes and the character count of the output, never the audio or the transcript itself. Logs leak; user content shouldn't.
- **Token counts when available** — included from Anthropic's `usage` block. Lays the groundwork for a future cost-tracking dashboard without changing the log format.

The logger setup itself lives in `backend/app/core/logging_config.py`. It installs `python-json-logger`'s `JsonFormatter` on the root logger and clears uvicorn's three internal loggers so their messages also come out as JSON, not pretty-printed. That detail matters: if uvicorn's startup banner is plain text and your app's logs are JSON, downstream parsers choke on every other line.

---

## LogQL — the queries behind the dashboard

LogQL is Loki's query language. It looks like PromQL with an extra log-selection step in front. A few real examples from the dashboard:

**Calls per minute, broken down by provider type:**
```logql
sum by (provider_type) (
  count_over_time(
    {compose_service="backend"} | json | event="ai_api.call" [1m]
  )
)
```

**Error rate over the last 5 minutes:**
```logql
100 * (
  (sum(count_over_time({compose_service="backend"} | json | event="ai_api.call" | status="error" [5m])) or vector(0))
  /
  sum(count_over_time({compose_service="backend"} | json | event="ai_api.call" [5m]))
)
```

The `or vector(0)` is load-bearing. Without it, a five-minute window with zero errors returns an empty vector, not zero, and `empty / N = empty` — the panel shows "No data" instead of `0%`. Easy to miss, easy to fix.

**P95 latency per provider:**
```logql
quantile_over_time(0.95, {compose_service="backend"} | json | event="ai_api.call" | unwrap duration_ms [5m]) by (provider)
```

`unwrap duration_ms` is what lets LogQL treat the JSON field as a number instead of a string. Without it, `quantile_over_time` has nothing numeric to compute on.

---

## The dashboard

Four panels, in order of "how often I'd actually look at this":

1. **AI API calls per minute** — time series, one line per `provider_type`. Tells you whether traffic is flowing at all.
2. **Total AI API calls (last 1h)** — single big number. The dashboard's at-a-glance health check.
3. **Error rate % (5-min rolling)** — time series, error count over total. The thing alerts fire on.
4. **API latency p50/p95 (ms)** — time series, one line per provider × per quantile. Catches "Claude got slow this morning" before users complain.

Provisioning lives in `observability/grafana/provisioning/datasources/loki.yml`, which auto-registers Loki on first boot. The dashboard itself is currently UI-managed and persisted in `grafana_data` volume; exporting to JSON and committing it alongside the datasource config is a natural next step toward fully dashboard-as-code.

---

## Alerting

One rule wired up: **`High AI API error rate`**, in the `voicepolish-alerts` folder, evaluated every minute by the `ai-api-monitoring` group. It uses the same error-rate query as the dashboard, with `WHEN QUERY IS ABOVE 10` and a two-minute pending period — meaning the threshold has to hold for two consecutive evaluations before the alert fires. That's deliberately conservative: a single transient spike from a momentary API blip shouldn't page anyone.

The contact point is `empty` for now — alerts surface in Grafana's Alerting UI but don't dispatch email or Slack messages. Wiring real notifications takes either an SMTP block in the Grafana config or a webhook URL from Slack/Discord; both are five-minute additions when this moves out of the lab.

To verify the path actually works end to end, the Anthropic API key was temporarily corrupted to force a wave of `401 AuthenticationError` responses. The Loki query, the dashboard panel, and the alert evaluation all picked it up exactly as designed. That kind of fault injection is the only honest way to know an alerting setup is real.

---

## Lessons from the build

A few things that took longer than expected and would have taken less with a checklist:

- **`docker compose restart` does not reload `env_file`.** The container's environment is frozen at creation time; restarting the process inside doesn't re-read the file. `docker compose stop <svc> && docker compose up -d <svc>` is the working incantation when you've changed an env var.
- **Promtail and Loki ship from the same repo but version independently.** Promtail is in extended maintenance and stopped at `3.6.11`; Loki keeps moving. Pinning both to "the same version" silently breaks `docker pull`.
- **Grafana 13's alert UI is a "Simplified" flow.** What used to be three expressions (query → reduce → threshold) is now a single `WHEN QUERY IS ABOVE N` row. The mental model is unchanged; the buttons moved.
- **Empty vectors vs. zero**. LogQL's strict-typing here is a feature in big setups (you don't want fake zeros polluting your aggregation), but it surprises everyone the first time their "error rate" panel shows "No data" when the answer is just "zero errors so far."

---

## What this isn't (yet)

Things the lab deliberately skips, and what production would add:

| Concern | Lab choice | Production-ish next step |
|---|---|---|
| Log storage | Local filesystem volume | S3 / GCS backend with retention by class |
| Retention | 30 days, single tier | Hot/cold tiering, longer cold retention |
| Authentication | Single admin user, password in `.env` | OAuth/SSO, no shared admin |
| Alerting destination | `empty` contact point | Slack webhook (5 min) or SMTP (10 min) |
| Dashboard provisioning | UI-managed, lives in volume | JSON exported, version-controlled |
| Trace correlation | None | OpenTelemetry with request IDs threaded through logs |
| Metrics | None | Prometheus + `/metrics` endpoint on the backend |

None of these are hard to add; they were just out of scope for "demonstrate the observability pattern end to end."

---

## Files added or changed

```
.env                                            (gitignored — Grafana admin password)
.env.example                                    (template)
docker-compose.yml                              (2 services → 5)
backend/requirements.txt                        (+ python-json-logger==4.1.0)
backend/app/main.py                             (+ configure_logging() call)
backend/app/core/logging_config.py              (new — JsonFormatter + uvicorn integration)
backend/app/services/polish_service.py          (added structured ai_api.call event)
backend/app/services/transcribe_service.py     (same)
observability/loki-config.yml                   (new)
observability/promtail-config.yml               (new)
observability/grafana/provisioning/datasources/loki.yml  (new)
```

Total: ~250 lines of config, ~30 lines of application code.

---

## Try it

```bash
git clone <repo>
cd voicepolish
cp .env.example .env  # then edit GRAFANA_ADMIN_PASSWORD
docker compose up -d --build
```

- App: <http://localhost:8080>
- Grafana: <http://localhost:3000>  (admin / your password)

Record a clip, polish it, then watch the dashboard come alive.
