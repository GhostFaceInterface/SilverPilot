# SilverPilot V1 Source Feasibility Matrix

Stage: 5
Status: Yahoo live-paper documentation gate only; no runtime source approved yet
Last reviewed: 2026-06-21

This document is a hard gate before reference ingestion. It does not implement
fetching, does not approve a runtime provider, and does not change production
behavior.

Stage 1 scope is documentation-only. It does not change code, schema, runtime
configuration, providers, brokers, risk behavior, workers, deployment files, or
environment variables. Runtime source switching and non-dry-run production
backfill remain blocked.

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
- `YAHOO_SOURCE_RISK_STATUS = owner_accepted_paper_use_risk`
- `REAL_MONEY_ALLOWED = false`

Therefore Stage 6 reference ingestion remains blocked.

System scope:

- SilverPilot remains live-paper only. It does not place real bank orders and
  does not support real-money trading.
- Yahoo is a delayed public reference proxy only, not a trading or execution
  source.
- `SI=F` is a futures-style silver proxy. It is not spot silver, not an exact
  global silver price, and may include futures contract rollover behavior.
- `TRY=X` is a delayed/public FX proxy only.
- Kuveyt Turk public bank quotes are indicative bank execution approximations
  for paper simulation unless executable parity is separately verified.
- Any divergence between `SI=F`, spot XAG/USD, USD/TRY conversion, and Kuveyt
  Turk gram silver prices must be visible in reports before runtime use.

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
| Yahoo Finance `SI=F` / `GC=F` / `TRY=X` chart endpoints | Web-visible, but automated collection is not approved for runtime | Often useful, must be measured per interval/range | Often intraday, exact interval limits must be measured | Exchange/provider timestamps exist but delay and timezone semantics must be validated | Yahoo terms restrict automated collection/scraping and reuse without permission | Delayed public reference proxy for owner-accepted live-paper risk only; not runtime-approved |
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

## Yahoo Live-Paper Risk Position

Yahoo must not be marked `source_terms_status=approved` for V1. The target
documentation status for the Yahoo path is:

- `source_risk_status=owner_accepted_paper_use_risk`
- `approved_by=owner/manual`
- `approved_at=<timestamp>`
- `approved_scope=live-paper only`
- `approved_symbols=SI=F, TRY=X`
- `approved_timeframe=4h`
- `real_money_allowed=false`

Stage 2 status: these fields now exist as `reference_market_instruments`
metadata. The paper runtime bootstrap records owner/manual live-paper approval
for `SI=F` only; `GC=F` remains seeded but not owner-approved. This still does
not approve runtime source switching.

`SI=F` must be presented with hard caveats:

- It is not spot silver.
- It is not an exact global silver price.
- It is a futures-style continuous/reference proxy.
- It may include futures contract rollover behavior.
- It can diverge materially from Kuveyt Turk gram silver bank pricing.

## Delay And Data Feasibility Gate

Do not assume a universal 15-minute delay. Yahoo/CME delay is source-specific
and must be validated for the exact access path, symbol, interval, and session.
If the delay cannot be verified, Stage 6 must use conservative assumptions:

- `data_delay_seconds=1800`
- `timeframe=4h`
- `source_delay_status=assumed_conservative`
- health target: `degraded_not_failed`

Yahoo 4h/2y feasibility output must record:

- whether the returned interval is actually `4h`;
- timestamp timezone semantics;
- missing bars or gaps;
- weekend bars, if any;
- final-bar lag in minutes at fetch time;
- whether repeat fetches produce the same `data_hash`;
- fail-closed behavior with degraded source health for rate limits or blocks.

Dry-run summary review is mandatory before any backfill write. The backfill CLI
requires `--reviewed-dry-run-id` for non-dry-run Yahoo writes. Runtime switching
is explicitly out of scope for Stage 2.

## Preferred Path

Preferred production-quality path:

1. Use a licensed/terms-approved reference market source for silver, ideally an
   exchange-grade SI/XAG family source with explicit timestamps and session
   calendar.
2. Use a matching or explicitly compatible FX source for USD/TRY.
3. Start with `4h` bars only after historical depth and session handling are
   validated. `1h` is allowed only after explicit timestamp, delay, FX, and
   quote-lag validation; `15m` is rejected for V1.
4. Store raw provider payload hashes and normalized bars separately from bank
   execution bars.

Preferred low-cost research path:

1. Implement Yahoo as `yahoo_research`, not as a runtime-approved source.
2. Start with offline fixtures and parser tests for `SI=F`, `GC=F`, and
   optional `TRY=X`.
3. Allow bounded manual dry-run backfill through
   `silverpilot-backfill-reference` only when the matching Yahoo path is labeled
   `source_risk_status=owner_accepted_paper_use_risk`, scoped to live-paper
   only, and `data_delay_seconds` is explicitly configured. Write backfill
   remains blocked until a dry-run summary has been reviewed.
4. Seed `SI=F` and `GC=F` as research-only reference instruments. Do not seed
   `TRY=X` into `reference_market_instruments`; FX source modeling needs a
   separate schema/service decision.
5. Use `4h` as the default research timeframe. `1h` may be measured during the
   spike. `15m` remains blocked for V1 runtime.
6. Record observed history depth, interval support, timestamp quality, delay
   policy, duplicate behavior, and data hash results before any runtime source
   decision.
7. Keep runtime ingestion disabled until explicit owner approval records the
   paper-use scope and the Stage 6 checklist is complete.

Research smoke result on 2026-06-21:

- `silverpilot-backfill-reference --source yahoo_research --symbol SI=F
  --timeframe 4h --period 2y --data-delay-seconds 900 --dry-run` fetched 2476
  normalized bars and wrote no market bars. Data hash:
  `89c03722a84612079950ad89d5187bdcc5de2fe5a5018bbcb4407f56d92a0cdc`.
- `silverpilot-backfill-reference --source yahoo_research --symbol GC=F
  --timeframe 4h --period 2y --data-delay-seconds 900 --dry-run` fetched 2478
  normalized bars and wrote no market bars. Data hash:
  `81d92e76b74f4a3029b95a6744c1bd170dcd97e4b99e51737e620d13e5b80b6a`.
- The `900` second delay used in the smoke is an explicit research parameter,
  not an approved source delay. Runtime use remains blocked until the Stage 6
  entry checklist is filled.
- Stage 1 does not accept `900` seconds as a verified Yahoo delay. If source
  delay cannot be independently verified, use the conservative 1800-second
  assumption above and report source health as degraded, not failed.

Research write smoke result on 2026-06-21:

- Against a throwaway SQLite DB, non-dry-run `SI=F` backfill inserted 2470 4h
  bars. Re-running the same command inserted 0 rows and updated 2470 existing
  rows with the same hash:
  `f1654595b5d028bd2dfe58267ddc0562e2b6eac9a12b66b2af65e44ebf342ba9`.
- Against the same throwaway DB, non-dry-run `GC=F` backfill inserted 2472 4h
  bars. Re-running the same command inserted 0 rows and updated 2472 existing
  rows with the same hash:
  `689599c77c10bdc2521addac703653318ee9a95f6786eaa176e18cdc9fef7c60`.
- Sample persisted rows had `data_delay_seconds=900`, `is_backfilled=true`,
  `data_quality_status=ok`, and populated `signal_available_at`. The observed
  local ingestion delay setting made the smoke offset 4500 seconds after
  `bar_end_at`; this remains a research measurement, not a runtime policy.
- Indicator smoke on the same throwaway DB calculated EMA 50, EMA 200, RSI 14,
  ATR 14, ADX 14, and Bollinger Band Width 20 from `SI=F` reference bars at
  `bar_end_at=2026-06-19T04:00:00` with
  `signal_available_at=2026-06-19T05:15:00`. This confirms the indicator
  service can consume persisted research reference bars, but runtime strategy
  switching remains blocked.
- Runtime source-selection regression now verifies that a paper tick configured
  with a reference instrument uses the latest reference bar whose
  `signal_available_at` has elapsed and ignores a newer unavailable reference
  bar. Bank quote collection still builds the execution bar separately.

No source should be silently chosen. Stage 6 must not start until this document
is updated with explicit approved values for reference source, FX source,
timeframe, history depth, timestamp policy, session calendar, owner-approved
paper-use scope, and source risk status. Yahoo must not be promoted by changing
its terms status to approved.

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
| Reference source risk status | none |
| Reference approval scope | none |
| Real-money allowed | false |
| FX source | none |
| FX symbol/pair | none |
| FX timestamp policy | none |
| FX terms/licensing status | none |
| Fixture source and data hash policy | none |
| Manual approval owner/date | none |
