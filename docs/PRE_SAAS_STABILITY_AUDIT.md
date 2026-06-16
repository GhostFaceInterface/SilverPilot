# Pre-SaaS Stability Audit

Date: 2026-06-12

Scope: local read-only architecture audit plus one behavior-preserving
stabilization patch. Production/VPS actions were not run.

Canonical baseline: `docs/PHASE_PLAN.md` remains the phase authority. This
audit summarizes verified code state and stabilization gaps before larger SaaS
work.

## Executive Summary

- API runtime is still paper-only by default: `Settings.real_money_enabled`
  defaults false and `auto_trading_mode` defaults `diagnostic`.
- Indicator storage and readiness support `technical-indicators-v2`; collector
  indicator generation loops over `1d`, `1h`, and `5m`.
- Auto-trader execution already consumes the canonical `1d -> 1h -> 5m`
  policy and records it in signal details. This audit made that same policy
  visible through `/indicators/readiness?include_policy=true`.
- Current code has a persisted `TradeIntentRecord`/`trade_intents` audit
  chain linked to decision runs, signals, risk decisions, and paper trades.
  Earlier notes in this audit about a missing table are stale 2026-06-12
  findings retained as historical context.
- ML is mostly advisory by default, but `risk_ml_decision_mode="hard_veto"` is
  supported by code and must remain explicitly gated out of the canonical path
  until Phase Plan Slice 4 is accepted.
- Mutating paper-trade and collector run endpoints still lack agent-token auth.
  Agent routes mostly use `verify_agent_token`, but the Telegram webhook has no
  shared-secret validation.
- Raw LLM prompt/response fields exist and can be accepted by `/agent/trace`;
  redaction-disable controls are not closed.

## Stabilization Change Applied

### Indicator Readiness Policy Visibility

Evidence:

- `apps/api/app/services/auto_trader.py` uses `get_strategy_timeframe_contexts`
  and `evaluate_timeframe_guardrails` for `1d`, `1h`, and `5m`.
- `apps/api/app/services/indicator_readiness.py` now owns
  `STRATEGY_TIMEFRAME_ROLES` and `STRATEGY_TIMEFRAME_POLICY`.
- `apps/api/app/api/routes.py` keeps the default single-frame readiness
  response, and adds optional `include_policy=true` policy readiness details.
- `apps/api/tests/test_indicator_readiness.py` now covers the policy response.

Risk: LOW. The default endpoint response remains backward compatible; new
fields are optional and only populated when requested.

Test status: PASS with `PYTHONPATH=apps/api pytest
apps/api/tests/test_indicator_readiness.py -q`.

## Findings

### F1. Readiness Endpoint Previously Hid The Runtime Timeframe Policy

Severity: LOW, fixed locally.

Evidence:

- `docs/PHASE_PLAN.md` states runtime timeframe policy is `1d` trend, `1h`
  entry, `5m` execution freshness.
- Auto-trader consumed all three frames, but `/indicators/readiness` only
  exposed one requested frame by default.

Recommended fix: keep single-frame default and expose the canonical policy on
request.

Test status: PASS. Added route regression for `include_policy=true`.

### F2. Trade Intent Audit Chain Was Not Persisted In The 2026-06-12 Snapshot

Severity: HISTORICAL. Current code has since added a persisted trade-intent
audit chain.

Historical evidence from this audit snapshot:

- `apps/api/app/services/trade_intents.py` defines `TradeIntent` as a dataclass
  and executes through `execute_trade_intent`.
- At the time of this audit snapshot, `apps/api/app/models/entities.py` had
  `Signal`, `RiskDecision`, `PaperTrade`, and `NotificationAudit`, but no
  persisted trade-intent model/table.

Current status: `TradeIntentRecord` exists and the auto-trader executes
through `execute_trade_intent`; real-money execution remains disabled and the
system does not auto-promote `diagnostic` mode to `paper`.

Recommended follow-up: keep the audit chain covered while finishing remaining
Phase 5 risk policy breadth.

### F3. Mutating Endpoint Auth Is Incomplete

Severity: HIGH before SaaS or public exposure.

Evidence:

- `apps/api/app/api/routes.py` protects many `/agent/*` endpoints with
  `verify_agent_token`.
- Mutating routes `/paper-trades`, `/collectors/manual-price`,
  `/collectors/*/run`, and `/agent/telegram/webhook` do not require
  `verify_agent_token`.
- `verify_agent_token` fails open when `agent_api_token` is unset, which is
  acceptable for local defaults but should fail closed in production for
  mutating routes.

Recommended fix: add production-aware auth policy for mutating endpoints, with
clear local/test bypass. Add tests for missing, wrong, and valid token paths.

Test status: Existing `test_agent_routes.py` passed. Mutating paper/collector
auth coverage still needs new tests with the future auth policy.

### F4. Telegram Webhook Has No Secret Validation

Severity: HIGH for webhook mode.

Evidence:

- `apps/api/app/api/routes.py` accepts `/agent/telegram/webhook` updates when a
  bot token is configured, then enqueues `process_telegram_update`.
- `apps/api/app/core/config.py` has `telegram_bot_token`,
  `telegram_webhook_url`, and `telegram_bot_mode`, but no webhook secret field.
- `apps/api/app/agents/telegram_bot.py` registers the webhook URL without a
  secret token check.

Recommended fix: add a `telegram_webhook_secret` setting, pass it to Telegram
webhook registration, validate Telegram's secret header on inbound requests,
and test reject/accept cases.

Test status: Existing Telegram tests passed. They cover redaction and behavior,
not webhook secret validation.

### F5. Raw LLM Trace Storage Remains Open

Severity: MEDIUM/HIGH depending on production exposure.

Evidence:

- `apps/api/app/models/entities.py` defines `LLMCallTrace.prompt_raw` and
  `response_raw`.
- `apps/api/app/schemas/agent.py` accepts `prompt_raw` and `response_raw`.
- `apps/api/app/api/routes.py` writes those fields in `/agent/trace`.
- `docs/DATA_CONTRACTS.md` says raw payload dumps and secrets must not be
  stored.

Recommended fix: redact or disable raw prompt/response storage by default,
store summaries/metadata instead, and require explicit local-only opt-in.

Test status: Not changed in this pass.

### F6. ML Advisory Boundary Is Mostly Preserved, But Hard Veto Exists

Severity: MEDIUM.

Evidence:

- `Settings.risk_ml_decision_mode` defaults to `advisory`.
- `apps/api/app/risk/service.py` records ML inference audits and only blocks on
  `ML_UNPROFITABLE_PREDICTION` when mode is `hard_veto`.
- `apps/api/tests/test_ml.py` explicitly covers advisory and hard-veto modes.
- `docs/PHASE_PLAN.md` keeps ML non-canonical until deterministic core and
  risk gaps are complete.

Recommended fix: keep production/default config advisory-only until Phase Plan
Slice 4 is accepted; add deployment config check that rejects accidental
`hard_veto` in canonical runtime.

Test status: `test_ml.py`, `test_dataset.py`, and `test_backtest.py` passed.

### F7. `XAG` And `XAG_GRAM` Boundary Is Improved But Not Fully Unified

Severity: MEDIUM.

Evidence:

- Runtime trading defaults to `XAG_GRAM`.
- Collector and ML paths still use `XAG` in global reference contexts.
- `docs/PHASE_PLAN.md` Slice 4 requires ML/backtest/dataset unification around
  `XAG_GRAM` or an explicit `XAG -> XAG_GRAM` normalization contract.
- `apps/api/app/collectors/service.py` replicates global `XAG` snapshots into
  `XAG_GRAM` using conversion logic.

Recommended fix: document and enforce the normalization boundary in ML,
dataset, backtest, and risk feature extraction before SaaS packaging.

Test status: Existing `test_saas_and_conversions.py`, `test_ml.py`,
`test_dataset.py`, and `test_backtest.py` passed.

### F8. SaaS Tables Exist, But Runtime Isolation Is Not Complete

Severity: MEDIUM.

Evidence:

- `apps/api/alembic/versions/e0f7a634cb21_add_saas_tables.py` adds
  `providers`, `tenant_portfolios`, `strategy_parameters`, and
  `asset_conversions`.
- `apps/api/app/models/entities.py` maps those tables.
- Core runtime endpoints still default to `gram-paper` and `XAG_GRAM` without a
  tenant boundary.

Recommended fix: defer broad SaaS refactor until Phase 4/5 gaps close. When
started, add tenant-aware service boundaries before exposing write paths.

Test status: Existing SaaS/conversion tests passed. They are not sufficient for
multi-tenant runtime isolation.

## Production Read-Only Smoke Plan

Do not run without explicit target confirmation and approval.

Recommended read-only endpoints:

- `GET /health`
- `GET /collectors/validation-gate`
- `GET /indicators/readiness?asset_symbol=XAG_GRAM&timeframe=5m&include_policy=true`
- `GET /risk/status`
- `GET /signals/latest`

Recommended read-only DB summaries:

- Latest collector runs by source and status.
- Fresh `price_snapshots` counts for `XAG` and `XAG_GRAM`.
- `market_bars` and `technical_indicators` counts by timeframe/source.
- Latest `signals`, `notification_audits`, `risk_decisions`, and
  `ml_inference_audits`.
- Confirm no production mutation was performed during the audit.

## Deploy Package Draft

No deploy, restart, migration, SSH, or production smoke was run.

Before deploy:

- Run the targeted local suites listed in the verification section.
- Review migration state with local `alembic history` and `alembic current`.
- Confirm target environment and exact revision.
- Confirm rollback command and previous image/revision.

After approved deploy:

- Restart only the intended services.
- Smoke `/health`, `/collectors/validation-gate`, policy readiness,
  `/risk/status`, and latest signal/notification audit.
- Block rollout if migration status, readiness, or rollback state is UNKNOWN.

## Verification

Executed:

```bash
PYTHONPATH=apps/api pytest apps/api/tests/test_indicator_readiness.py -q
PYTHONPATH=apps/api pytest apps/api/tests/test_collectors.py apps/api/tests/test_indicator_readiness.py apps/api/tests/test_auto_trader.py apps/api/tests/test_telegram.py -q
PYTHONPATH=apps/api pytest apps/api/tests/test_ml.py apps/api/tests/test_dataset.py apps/api/tests/test_backtest.py -q
PYTHONPATH=apps/api pytest apps/api/tests/test_paper_trading.py apps/api/tests/test_trade_intents.py apps/api/tests/test_saas_and_conversions.py apps/api/tests/test_agent_routes.py -q
PYTHONPATH=apps/api pytest apps/api/tests/test_docs_consistency.py -q
```

Result:

- `5 passed`
- `97 passed`
- `14 passed`
- `42 passed`
- `5 passed`

Still recommended before any deploy or SaaS work:

```bash
PYTHONPATH=apps/api pytest apps/api/tests -q
```
