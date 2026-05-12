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
