# Decisions

## D-001: Single Memory Bank

Status: accepted.

Use one canonical memory bank and short `agents/*.md` files. Separate large memory banks per agent are rejected because they create synchronization and duplication risk.

## D-002: Backend Owns Decisions

Status: accepted.

LLM agents may explain or critique decisions, but the deterministic backend risk engine owns paper-trading decisions.

## D-003: No ML in Early Phases

Status: accepted.

ML starts only after reliable data collection, paper trading, risk policy, and backtesting exist.

## D-004: Raw Data Is Append-Only

Status: accepted.

Collector raw data is preserved for auditability and future dataset reconstruction. Normalized tables and derived features are separate.

## D-005: Structured Agent Output Required

Status: accepted.

Agent responses must validate against Pydantic/JSON-schema contracts once LLM features exist. Free-form text can appear in reports, not in decision paths.

## D-006: Streamlit Before Custom Dashboard

Status: accepted.

Use Streamlit first for speed and observability. Move to Next.js only after backend records and workflows stabilize.

## D-007: Runtime Memory Belongs In PostgreSQL

Status: accepted.

Markdown is development memory for agents and maintainers. Runtime data such as prices, trades, reports, agent outputs, LLM usage, backtests, and dataset versions must be stored in PostgreSQL once implemented.

## D-008: Definition Of Done Is Required

Status: accepted.

Implementation tasks must define scope, exclusions, validation, and completion criteria before work starts. A task is not complete until validation runs and `docs/WORKLOG.md` is updated.

## D-009: LLM Outage Must Not Break Core System

Status: accepted.

The backend must continue collecting data, calculating portfolio state, running risk rules, and serving dashboard data without LLM provider availability.

## D-010: Agent Budget Guards Are Mandatory

Status: accepted.

Production agent calls must enforce token and cost limits. Strong model usage should be rare, justified, and traceable.

## D-011: VPS Access Uses SSH Alias

Status: accepted.

VPS access for deployment work uses local SSH alias `silverpilot-vps`. This avoids exposing IP addresses or private connection details in prompts and keeps agent instructions stable.

## D-012: Free Public Data Sources First For MVP

Status: accepted.

Paid market-data APIs are disabled for MVP. Collectors may use official free APIs, public pages, RSS feeds, and no-cost API-key tiers only when no login bypass, paid access, private endpoint reverse engineering, or aggressive scraping is required.

## D-013: CI First, VPS Smoke Manual

Status: accepted.

GitHub Actions runs tests, Docker Compose validation, and API image build automatically on push and pull request. VPS deployment and smoke checks are manual because they require server secrets and can mutate the running VPS.

## D-014: FRED First For Macro MVP

Status: accepted.

FRED is the MVP macro-series gateway when a free `FRED_API_KEY` is configured. BLS-origin CPI, PPI, and labor series should be consumed through FRED first to avoid adding a direct BLS integration before it is necessary.

## D-015: Direct BLS Deferred

Status: accepted.

The direct BLS API collector is outside MVP. `BLS_API_KEY` may remain an optional/backlog env placeholder, but no direct BLS implementation is planned until explicitly re-approved.

## D-016: Türkiye Data Is Execution Context

Status: accepted.

Türkiye sources such as TCMB daily XML, optional EVDS, TÜİK, Resmi Gazete, GİB, and Hazine ve Maliye Bakanlığı matter for TRY execution simulation, bank spread comparison, local risk, and tax/rule verification. They are not treated as primary global silver direction signals.

## D-017: Advanced Agent Memory Deferred

Status: superseded by D-018.

Zep/Graphiti, Mem0, Cognee, LightRAG, Letta, and similar memory layers remain research/backlog. The MVP uses markdown for development memory and PostgreSQL for runtime memory; any future graph memory must exclude raw collector data.

## D-018: PostgreSQL-First Lightweight Runtime Memory

Status: accepted.

SilverPilot will implement a custom PostgreSQL-based runtime memory layer before considering external memory frameworks. This lowers operational load, fits the current 4 vCPU / 6 GB VPS, keeps memory records auditable, avoids paid memory platforms, and can later evolve to `pgvector` or external graph memory only if proven necessary.

Explicitly excluded for now:

- Zep.
- Graphiti.
- Neo4j/FalkorDB memory stack.
- Cognee.
- LightRAG.
- Letta.
- Mem0 production integration.

## D-019: Bank Silver Price Gates Phase 4

Status: accepted.

Phase 4 risk engine work will not start until execution-critical bank silver buy/sell pricing is resolved. Kuveyt Türk official public page data is the primary source when public browser-loaded finance portal data can be parsed without login or bypass behavior. Manual bank-price input is allowed only as a visible degraded simulation fallback, not as a production collector.

## D-020: Global XAG/USD Uses Approved Fallbacks

Status: accepted.

Stooq current CSV remains the primary public global XAG/USD source, but Phase 4 readiness must not depend on Stooq alone because VPS network timeouts have been observed. The collector uses a configurable `GlobalSilverPriceProvider` priority list. Gold-API free no-auth JSON is an approved fallback, and Metals.Dev is an optional free API-key fallback disabled when no key is configured. Paid APIs, payment-required tiers, login/captcha/paywall bypass, and fake/stale price reuse remain excluded.

Stooq failure degrades source reliability but does not block Phase 4 when an approved fallback global XAG/USD value is fresh. Missing or stale global XAG/USD still blocks Phase 4.

## D-021: Paper Trades Must Reference Deterministic Risk Decisions

Status: accepted.

Phase 4 starts by making paper trading depend on the backend risk engine. Every persisted paper-trade record must reference a persisted `risk_decisions` row. Policy-blocked buy/sell attempts are recorded as `paper_trades.action=blocked` with no cash or position mutation, so the user can inspect why the action was blocked. The first implemented blocks are missing/stale execution-critical data, excessive spread, insufficient paper cash, and insufficient paper position. Real-money execution, bank automation, LLM decisions, volatility/FOMO strategy rules, and dashboard work remain excluded from this slice.

## D-022: Global XAG Risk Metrics Are Source-Aware

Status: accepted.

Phase 4 global XAG/USD volatility and FOMO checks compute risk metrics per source and use the highest source-specific metric for blocking. Combined cross-source min/max/range remains visible in `/risk/status` diagnostics, but source switching between Stooq, Gold-API, and optional Metals.Dev must not create synthetic volatility or FOMO blocks by itself.

## D-023: Make OpenClaw Mandatory For The Agent Orchestration Layer

Status: accepted.

SilverPilot will use OpenClaw as the mandatory agent orchestration layer once the deterministic core, dashboard, LLM gateway, and runtime memory boundaries are ready.

Rationale:

The original project vision included OpenClaw as the multi-agent finance assistant layer. The current backend-first architecture remains correct, but OpenClaw must be explicitly integrated into the roadmap instead of treated as optional.

Consequences:

- Backend remains deterministic and authoritative.
- OpenClaw becomes the required runtime for higher-level agents.
- OpenClaw is introduced only after safe boundaries exist.
- Project-local skills are preferred over third-party skills.
- OpenClaw receives sanitized context from backend APIs and memory services.
- OpenClaw cannot execute trades, access bank systems, or bypass risk rules.

Supersedes:

- Any previous decision or planning note that marked OpenClaw as optional, implicit, or backlog-only.
