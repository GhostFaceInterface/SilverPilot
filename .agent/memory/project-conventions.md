---
type: project
created: 2026-05-18
updated: 2026-05-18
---

# Project Conventions & Core Brief

## 1. Project Purpose
SilverPilot is a backend-first, silver paper-trading intelligence system designed to simulate trading scenarios with a virtual 600 USD balance.

## 2. Tier 0 Rules (Strict Core Policy)
- **No Real Money:** Strictly virtual paper-trading.
- **No Bank Automation:** No real-world bank account API integration.
- **No Automatic Real Trades:** System cannot mutate real money assets.
- **LLM Independence Pattern:** The system must continue working if LLM APIs are unavailable. Core prices collection, risk rules, and paper trading must remain fully operational.

## 3. Decision Ownership & Data Flow
- The backend core holds absolute authority over trade executions and risk decisions.
- LLM agents (Hermes/OpenClaw) can summarize, explain, classify, or critique, but they do NOT execute or modify trades.
- Data Flow:
  `collectors` -> `raw data` -> `normalized snapshots` -> `risk engine` -> `paper trading engine` -> `reports`
