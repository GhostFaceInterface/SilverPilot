# SilverPilot V1 Source Feasibility Matrix

Stage: 5
Status: feasibility documented; no runtime source approved yet
Last reviewed: 2026-06-20

This document is a hard gate before reference ingestion. It does not implement
fetching, does not approve a runtime provider, and does not change production
behavior.

## Decision Summary

V1 policy remains:

- `IndicatorSourcePolicy = reference_market_first`
- `ExecutionSourcePolicy = account_bound_bank_quote`

Stage 5 outcome:

- `APPROVED_REFERENCE_SOURCE = none`
- `APPROVED_FX_SOURCE = none`
- `APPROVED_TIMEFRAME = none`
- `APPROVED_HISTORY_DEPTH = none`
- `APPROVED_TIMESTAMP_POLICY = none`
- `APPROVED_SESSION_CALENDAR = none`
- `APPROVED_TERMS_STATUS = not_approved`

Therefore Stage 6 reference ingestion remains blocked.

## Source Requirements

A V1 reference source must provide, or be safely wrapped with:

- public web-fetchable access without auth, private endpoints, login, captcha, or
  mobile banking APIs;
- stable symbol identity and source provenance;
- enough historical bars for indicator warm-up and backtests;
- explicit bar timestamps and timezone policy;
- session calendar or a documented source-specific availability policy;
- terms/licensing status approved for SilverPilot's intended use;
- deterministic fixtures before live collection;
- no real-money execution capability.

A V1 FX source must provide USD/TRY conversion with comparable timestamp quality
to the selected reference source. If the FX timestamp is daily while the metal
reference is intraday, intraday strategy switching must remain blocked or the
timeframe must be reduced to daily.

## Reference Market Candidates

| Candidate | Public no-key fetch | Historical depth | Intraday | Timestamp/session | Terms/licensing | V1 status |
| --- | --- | --- | --- | --- | --- | --- |
| CME official silver futures data, such as SI futures | Not approved as free/no-key runtime access | Strong through official data products | Yes through licensed feeds/products | Strong exchange session calendar | CME presents real-time and historical market data as data products; licensing required for practical use | Best quality, not approved for free V1 runtime |
| Yahoo Finance `SI=F` / `XAGUSD`-like pages or chart endpoints | Web-visible, but automated collection is not approved | Often useful | Often intraday | Exchange timestamps exist but must be validated | Yahoo terms restrict automated collection/scraping and reuse without permission | Research only; not approved |
| Stooq commodity or futures symbols | Possibly public, but current web access can require browser verification | Unknown until manually verified | Unknown | Unknown | Terms and automated collection suitability not yet verified | Research only; not approved |
| Kuveyt Turk public `GUMUS ONS/$`-style row, if available | Public finance portal | Sparse/current only unless stored by us | Indicative updates only | Bank/source session ambiguous | Same public bank indicative limitation as execution quotes | Diagnostic only; not V1 reference source |
| LBMA Silver Price | Public information page; tabulated data requires portal/licence path | Licensed historical benchmark | No, daily auction benchmark | Daily London auction, not weekends/UK holidays | IBA licence required for many valuation/pricing uses | Benchmark/future research only, not intraday V1 |
| Gold analogs, such as `XAUUSD` or gold futures | Similar constraints to silver equivalents | Depends on source | Depends on source | Depends on source | Separate source decision required | Future research only |

Evidence:

- CME describes real-time and historical market data as formal data products,
  including Datamine and real-time feeds:
  https://www.cmegroup.com/market-data.html
- CME publishes exchange trading-hours material that must be modeled as
  source-specific session policy:
  https://www.cmegroup.com/trading-hours.html
- LBMA states that Silver Price use for valuation/pricing and real-time or
  historical data access requires IBA licensing:
  https://www.lbma.org.uk/prices-and-data/precious-metal-prices
- Yahoo Terms restrict automated data collection and service-data reuse without
  permission:
  https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html

## Execution Quote Candidate

| Candidate | Public fetch | Buy/sell | Timestamp | Indicative/executable | V1 status |
| --- | --- | --- | --- | --- | --- |
| Kuveyt Turk public finance portal | Yes, current implementation uses official public finance portal assets | Yes for bank buy/sell fields | `provider_reported_at` remains null unless the source exposes one | Indicative only unless manually verified against internet/mobile branch | Approved only as indicative execution approximation for the bound paper account |
| Future Turkish banks | Not evaluated in this stage | Unknown | Unknown | Unknown | Blocked until separate feasibility |

Evidence:

- Kuveyt Turk's public finance portal says shown rates are indicative, not
  binding, and internet/mobile branch rates apply for transactions:
  https://www.kuveytturk.com.tr/finans-portali

Execution rule:

- A Kuveyt public quote can support paper execution simulation only when labeled
  `indicative_only` or equivalent.
- It must never be shown as a guaranteed executable price.
- It must never be used for best-bank routing.

## FX Conversion Candidates

| Candidate | Public no-key fetch | Intraday | Timestamp/session | Terms/licensing | V1 status |
| --- | --- | --- | --- | --- | --- |
| Kuveyt Turk public USD/TRY quote | Yes through same public finance portal family | Indicative updates | Provider timestamp unknown unless exposed | Same indicative public-bank limitation | Useful for execution premium snapshots, not approved as independent reference FX |
| TCMB indicative exchange rates | Public official statistics | Daily/official indicative time series | Official daily statistics; not intraday | Official public statistics, but use policy still needs final review | Daily benchmark candidate only; not intraday V1 |
| Yahoo Finance `TRY=X` | Web-visible | Often intraday | Needs validation | Yahoo automated collection/reuse not approved | Research only; not approved |
| CME/EBS FX products | Official market data products | Yes | Strong session policy | Licensed/product access | Best quality, not approved for free V1 runtime |

Evidence:

- TCMB provides official indicative exchange-rate statistics and links long-run
  exchange-rate time series:
  https://www.tcmb.gov.tr/wps/wcm/connect/en/tcmb+en/main+menu/statistics/exchange+rates/indicative+exchange+rates

## Preferred Path

Preferred production-quality path:

1. Use a licensed/terms-approved reference market source for silver, ideally an
   exchange-grade SI/XAG family source with explicit timestamps and session
   calendar.
2. Use a matching or explicitly compatible FX source for USD/TRY.
3. Start with `1h` bars only after historical depth and session handling are
   validated.
4. Store raw provider payload hashes and normalized bars separately from bank
   execution bars.

Preferred low-cost research path:

1. Manually evaluate Stooq and Yahoo access/terms outside runtime.
2. If one is acceptable, add offline fixtures first.
3. Run deterministic parser and timestamp/session tests before any live fetch.
4. Keep runtime ingestion disabled until legal/terms approval is recorded.

No source should be silently chosen. Stage 6 must not start until this document
is updated with explicit approved values for reference source, FX source,
timeframe, history depth, timestamp policy, session calendar, and terms status.

## Stage 6 Entry Checklist

Stage 6 may start only when all rows below are filled with non-placeholder
values:

| Gate | Approved value |
| --- | --- |
| Reference source | none |
| Reference symbol/instrument | none |
| Reference access method | none |
| Reference timestamp policy | none |
| Reference session calendar | none |
| Reference historical depth | none |
| Reference timeframe | none |
| Reference terms/licensing status | none |
| FX source | none |
| FX symbol/pair | none |
| FX timestamp policy | none |
| FX terms/licensing status | none |
| Fixture source and data hash policy | none |
| Manual approval owner/date | none |

