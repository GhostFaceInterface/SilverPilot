# Phase 2A Audit: Kuveyt Turk Feasibility

## ROADMAP Objective

Prove whether public Kuveyt Turk silver quotes can be fetched legally,
technically, and reliably before implementing a provider. Record the source
assumptions in `ROADMAP.md`; do not create scraping code in this phase.

## Current Evidence

- `ROADMAP.md` contains the canonical feasibility result dated 2026-06-17.
- Official public assets inspected there include `robots.txt`, the live silver
  page, the finance portal page, and public JavaScript endpoint discovery.
- The roadmap records the last-known public finance portal JSON path and the
  parities endpoint discovered from official assets.
- The roadmap explicitly states that the displayed rates are indicative and not
  binding executable prices.

## Required Interfaces And Schema

No code interface is required for Phase 2A. The required output is source-backed
policy and feasibility text in `ROADMAP.md`.

## Data Flow

Public official Kuveyt Turk pages are inspected manually. Findings are reduced
to provider constraints for Phase 2B: public endpoint only, semantic endpoint
discovery first, fail closed on schema or source drift, conservative polling,
and indicative labeling.

## Failure Modes

- Treating `robots.txt` as legal permission by itself.
- Treating indicative public rates as guaranteed executable prices.
- Depending on private, authenticated, captcha, login, or mobile-only paths.
- Hardcoding a volatile `/ck0d84?...` path as a stable contract.
- Assuming provider timestamps exist when the JSON has none.

## Exact Tests

Phase 2A is documentation-only. Its acceptance evidence is reviewed by reading
`ROADMAP.md`. Phase 2B converts these constraints into tests.

## Done Gate

`ROADMAP.md` clearly approves or blocks provider implementation with source
URLs, assumptions, limitations, freshness behavior, weekend/holiday notes, and
public indicative quote boundaries.

## Out Of Scope

- Provider code.
- Scheduled collectors.
- Other banks.
- Trading strategies or execution.
