# Phase 2B Audit: Kuveyt Turk Provider

## ROADMAP Objective

Implement the first provider after Phase 2A approval. The provider discovers the
public finance portal endpoint, parses Kuveyt Turk silver gram/TRY quotes,
checks freshness, fails visibly on bad source states, and avoids private or
authenticated endpoints.

## Current Evidence

- `src/silverpilot/app/providers/kuveyt_turk.py` implements
  `KuveytTurkEndpointResolver`, `KuveytTurkPriceProvider`, parser helpers, and
  freshness validation.
- `src/silverpilot/app/providers/errors.py` defines provider failure classes.
- `src/silverpilot/app/domain/interfaces.py` defines the `PriceProvider`
  protocol used by the collector.
- `tests/test_kuveyt_turk_provider.py` covers endpoint discovery, parser
  behavior, fail-closed cases, freshness errors, and instrument validation.

## Required Interfaces And Schema

- `PriceProvider.fetch_quote(instrument: BankInstrument) -> PriceQuote`.
- Provider-specific `fetch_quote_result` may return `source_hash`,
  `provider_reported_at`, and `indicative` metadata for collection.
- Persisted quotes use `price_quotes` from Phase 1.

Naming hygiene note resolved: the ambiguous `KUVEYT_TURK_FINANCE_PORTAL_URL`
alias is not exported. The last-known fallback data is named explicitly as
`LAST_KNOWN_FINANCE_PORTAL_PATH` and `LAST_KNOWN_FINANCE_PORTAL_URL`.

## Data Flow

The provider validates the requested instrument as XAG/GRAM/TRY, resolves the
current finance portal endpoint from public official assets, fetches JSON,
selects the unique `GMS (gr)` row, parses `BuyRate` and `SellRate`, validates
bank sell price is not below bank buy price, sets `observed_at` from the
provider timestamp when available or `fetched_at` otherwise, and returns an
indicative `PriceQuote`.

## Failure Modes

- Endpoint discovery missing from both finance portal page and core JavaScript.
- Endpoint path not matching the allowed same-site `/ck0d84?<hash>` pattern.
- Payload not valid UTF-8 or JSON.
- Missing, duplicate, or malformed `GMS (gr)` rows.
- Missing or invalid buy/sell fields.
- Stale or future observed timestamp.
- Unsupported instrument.
- Network, timeout, or HTTP failures.

## Exact Tests

- `pytest tests/test_kuveyt_turk_provider.py`
- Include fixtures for endpoint discovery through `addresses["fn-rlrtd"]` and
  fallback `ApiEndpoints.financePortal`.
- Include reject fixtures for external, login, private, mobile, malformed, and
  missing endpoint paths.
- Include parser fixtures for missing rows, duplicate rows, invalid prices, and
  stale data.

## Done Gate

All provider tests pass, the provider uses only public official assets, default
behavior discovers the endpoint dynamically, and every schema/source/freshness
drift path fails closed with explicit errors.

## Out Of Scope

- Other banks.
- Best-bank routing.
- Trading signals.
- Collector scheduling beyond single quote fetch support.
