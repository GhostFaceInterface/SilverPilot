# SilverPilot V1 Source Policy

This document records the current source-policy decision before implementation
changes. It is a Stage 1 documentation artifact only; it does not imply that the
runtime already enforces the policy below.

## Current Runtime Status

The current live paper runtime still collects Kuveyt Turk public bank quotes,
builds bank-derived `execution` bars, and may use those bars for warm-up,
indicators, regimes, and strategy decisions.

That behavior is not the final V1 policy. Until a reference market source and
FX source are approved, bank-native bars are diagnostic or legacy runtime data.

## V1 Policy

- `IndicatorSourcePolicy`: `reference_market_first`.
- `ExecutionSourcePolicy`: `account_bound_bank_quote`.
- Indicators, regimes, strategy signals, and reference-side backtests should use
  an approved `ReferenceMarketInstrument`.
- Risk, paper execution, spread, costs, premium/discount, valuation, and
  account-bound reports must use the account's own bank execution venue and
  bank buy/sell quote.
- Public Kuveyt Turk quotes are indicative execution approximation inputs unless
  executable parity with internet/mobile branch prices is manually verified.

Yahoo live-paper caveat: Yahoo data may be documented only as a delayed public
reference proxy with `source_risk_status=owner_accepted_paper_use_risk`. It is
not approved for real money, automated runtime collection, or execution.
`SI=F` is a futures-style continuous/reference silver proxy, not spot silver or
an exact global silver price, and it may include contract rollover behavior.
`TRY=X` is a delayed/public FX proxy only.

## Freshness And Usability Rules

- `fetched_at` means SilverPilot fetched the endpoint at that time.
- `provider_reported_at` means the provider exposed a reliable market/source
  timestamp. If the source does not expose one, it must remain null.
- Endpoint freshness is not market/session availability.
- Freshness is not quote usability.
- Quote usability must be decided by source, instrument, venue, and purpose.

Stage 3 status: `price_quotes` now stores nullable `provider_reported_at`,
`indicative`, `endpoint_status`, `market_session_status`, and `quote_usability`
metadata. This makes the distinction observable but does not yet change
RiskManager, PaperBroker, warm-up, or strategy behavior.

Stage 4 status: warm-up progress is now counted from bars eligible for the
configured indicator source policy. Under the default `reference_market_first`
policy, bank-derived execution bars remain visible as collected bars but do not
advance indicator warm-up. The `execution_bank_diagnostic` policy can count
bank-derived execution bars for diagnostic runs only; it is not the V1 default.

Purposes that must be distinguishable:

- collection
- warm-up
- indicator
- strategy
- risk
- execution
- valuation
- reporting

## Premium And Spread

Bank premium, discount, and spread must not be modeled as a static offset in V1.
They must be timestamped snapshots with source provenance because bank spreads
can change around nights, weekends, holidays, source degradation, and reference
market closures.

## Stage Gate

Reference bar ingestion and runtime source switching are blocked until source
feasibility approves:

- reference source
- FX source
- access method
- timestamp policy
- session calendar
- historical depth
- timeframe
- terms/licensing status
- owner-accepted paper-use risk status, if using the Yahoo path

If any item is missing, Stage 6 reference ingestion must not start.

Stage 5 status: the feasibility matrix lives in
`docs/source-feasibility-v1.md`. As of 2026-06-21 it approves no runtime
reference source and no FX source, so Stage 6 remains blocked.

## Delayed Reference Signal Rules

Phase 18 metadata primitives are now present in code before any provider is
approved. Reference bars must carry source provenance and, when the provider
supports it, `provider_reported_at`, `fetched_at`, `stored_at`,
`data_delay_seconds`, `signal_available_at`, session status, and data quality.

`signal_available_at` is the earliest decision time at which a bar may influence
indicators, regimes, strategies, or backtests:

`signal_available_at = bar_end_at + data_delay_seconds + ingestion_delay_seconds`

If a legacy diagnostic row has no `signal_available_at`, existing diagnostic
behavior may continue. New approved reference rows should populate it. Live
decisions must also require the row to have been stored by the decision time.

The V1 default timeframe is `4h`. `15m` remains rejected for V1 because source
delay, FX compatibility, and execution quote alignment are not yet proven. If
only daily official reference/FX data is approved, V1 must fall back to `1d`.
No universal 15-minute Yahoo/CME delay may be assumed. If Yahoo delay cannot be
verified for the exact symbol, interval, and access path, the conservative
policy is `data_delay_seconds=1800`, `timeframe=4h`,
`source_delay_status=assumed_conservative`, and source health
`degraded_not_failed`.

Execution quote selection remains account-bound. Risk uses the latest bank
quote at or before the decision time and rejects with
`missing_execution_quote` or `stale_execution_quote` when no eligible quote is
available within the configured lag window. The default maximum lag is 300
seconds.

Dry-run summaries must be reviewed before any reference backfill write. Runtime
source switching remains blocked outside an explicit later stage.
