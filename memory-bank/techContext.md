# Tech Context

## Planned Backend Stack

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Pydantic
- httpx
- tenacity
- Docker Compose

## Planned Data Stack

- Pandas
- Polars
- DuckDB
- NumPy

## Free Data Source Strategy

- FRED is the MVP macro-series gateway when `FRED_API_KEY` is configured.
- Direct BLS remains optional/backlog; use FRED-hosted BLS-origin series first.
- TCMB daily XML is the primary no-key USD/TRY source.
- TCMB EVDS is optional if a free user key is configured later.
- TÜİK automation is backlog; use it for low-frequency local macro context, not intraday decisions.
- Paid market-data APIs remain disabled for MVP.
- Fed RSS uses the official Federal Reserve monetary policy RSS feed by default and requires no API key.

## Planned LLM Stack

- OpenRouter first.
- LiteLLM later if routing, fallback, or budget proxying is needed.
- Langfuse before production agent usage.
- Instructor/Pydantic for structured output validation.
- OpenClaw is a roadmap-required future dependency for agent orchestration; it is not a current backend dependency.
- Phase 6 must define OpenClaw runtime target, workspace layout, provider routing, sandbox policy, tool allowlist/denylist, and secrets boundary before implementation.
- Research needed: OpenClaw Node/runtime requirements, local workspace security, browser/web research controls, project-local skill packaging, and audit/log integration.
- Current code does not read Langfuse settings yet; `.env.example` uses `LANGFUSE_HOST`, while the LLM gateway phase must choose and document the final env name before implementation.

## Runtime Memory Strategy

- Phase 6.5 uses custom PostgreSQL runtime memory tables.
- No Zep, Graphiti, Neo4j, FalkorDB, Cognee, LightRAG, Letta, or Mem0 production service is planned.
- Runtime memory stores compact operational facts, reliability summaries, decision summaries, disagreements, postmortems, and outcome notes.
- Runtime memory must not store raw payloads, full traces, secrets, SSH details, API keys, or bank details.
- `pgvector` may be evaluated later only if PostgreSQL-native semantic retrieval becomes necessary.

## Planned ML Stack

- LightGBM first.
- MLflow for model registry.
- AutoGluon/Chronos-Bolt only after baseline ML exists.
- Feast is optional and deferred.

## Infrastructure Access

- VPS access method: SSH alias `silverpilot-vps`.
- Usage: `ssh silverpilot-vps`.
- Current project path on VPS: `/opt/silverpilot/SilverPilot`.
- Runtime target: Ubuntu VPS with Docker installed.
- Agents must not read or expose SSH private keys or production secrets.
- Runtime secrets belong in VPS-local `.env.production`, not in markdown or git.

## CI/CD

- GitHub Actions workflow lives at `.github/workflows/ci.yml`.
- Push and pull request CI runs backend tests, Docker Compose config validation, and API image build.
- VPS smoke/deploy validation is manual and uses GitHub repository secrets.
- Workflow changes must stay aligned with project test commands and Docker Compose services.

## Phase 1 Backend Runtime

- API container uses Python 3.12.
- FastAPI serves the backend.
- SQLAlchemy 2.x owns ORM models.
- Alembic owns database migrations.
- PostgreSQL runs through Docker Compose.
- PostgreSQL is private to the Compose network by default.
- Initial endpoints are deterministic and do not require LLM providers.
- Token/cost discipline remains deferred to the LLM gateway phase; current backend must work without LLM availability.
