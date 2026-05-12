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

