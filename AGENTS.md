# AGENTS.md: PolicyGround for coding agents

PolicyGround answers policy questions for support agents. It resolves the subject in a
knowledge graph (Postgres), uses retrieval only for citations, and validates every date and
amount deterministically before an answer leaves the system. PLAN.md is the plan; every
design decision is in DECISIONS.md (D1…), every surprise in INCIDENTS.md, every
measurement in METRICS.md.

## Layout

| Path | What |
|---|---|
| `src/policyground/tenants/<t>/` | A tenant: `spec.yaml` (data) + `adapter.py` (generate / render / golden). `hotels` is the reference. |
| `src/policyground/tenant.py`, `kgmodel.py` | Spec loader/validator; generic KG model and reference resolver |
| `src/policyground/graph.py` | LangGraph answer path: route → kg_lookup → retrieve → answer → validate (→ regenerate ≤1 / abstain) |
| `src/policyground/validate.py`, `eval/score.py` | Deterministic validator and scorer (spec-driven) |
| `src/policyground/kg/`, `ingest/`, `retrieve.py` | KG load + lookup; chunk/embed/upsert; vector search |
| `src/policyground/eval/` | Golden-set eval, fault injection, retrieval comparison |
| `src/policyground/stream/`, `drift.py` | **Hotels-only demo machinery** (M4 Kafka mutations, drift). Don't generalise it. |
| `src/policyground/api.py`, `mcp_server.py` | HTTP API (`/ask`, `/metrics`); read-only MCP server (stdio) |
| `src/policyground/obs/` | JSON logs, Prometheus metrics (low-cardinality labels only), Phoenix tracing |
| `airflow/` | Airflow 3 DAG (own venv); `db/migrations/` SQL; `obs/` Prometheus/Grafana/Loki/Alloy configs |
| `.claude/skills/onboard-tenant/SKILL.md` | How to add a tenant. Follow it exactly. |

## Commands

```
make up                       # Postgres + Redpanda + observability (Docker)
make test                     # pytest (DB tests skip if Postgres is down)
make seed TENANT=<t>          # kg.json + corpus snapshot + golden set via the adapter
make ingest TENANT=<t>        # load KG + chunk/embed the latest snapshot
make eval TENANT=<t>          # LLM eval through the kg graph (costs ~$0.0004/question)
make check-tenant TENANT=<t>  # the mandatory onboarding done-check
```

Python 3.12 via `uv` (`uv sync`, `uv run …`). The API key is read from `.env`
(`ANTHROPIC_API_KEY`). Never print it, never commit `.env`.

## Conventions

- Database roles: `ingest_rw` writes data, `api_ro` reads, `grafana_ro` sees dashboards
  only. App code never connects as the admin.
- Logs go to stderr and `~/Library/Logs/policyground/`, **never stdout**: the MCP server
  speaks JSON-RPC on stdout.
- Metric labels only from `policyground.obs.metrics.ALLOWED_LABELS`. IDs belong in logs
  and traces.
- Deterministic generators: seeded `random.Random`, render choices through the Chooser.
- `hotels` data is a measured record: don't re-seed it, don't edit `data/hotels`.
- Don't push, open PRs, or deploy. Local commits only, and only when asked.
