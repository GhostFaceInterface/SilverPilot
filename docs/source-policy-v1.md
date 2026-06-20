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

If any item is missing, Stage 6 reference ingestion must not start.

Stage 5 status: the feasibility matrix lives in
`docs/source-feasibility-v1.md`. As of 2026-06-20 it approves no runtime
reference source and no FX source, so Stage 6 remains blocked.
