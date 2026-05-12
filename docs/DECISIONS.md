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

