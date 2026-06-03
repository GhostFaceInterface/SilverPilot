# SilverPilot Known Risks Registry

## 🚨 Critical Risks

### 1. Real-Money Protection Violation (TIER 0)
- **Risk:** Integration of real bank automation or broker interfaces.
- **Remediation:** Keep all operations strictly paper-trading. No actual API access keys for real bank accounts or real brokers should ever be stored.

### 2. Network Leakage in Test Environments
- **Risk:** Tests making live HTTP calls to scraper targets or LLM gateways when database news is empty.
- **Remediation:** Enforce complete mocking of data collectors in test suites. Never execute live scrapers under tests.

### 3. VPS Resource Exhaustion
- **Risk:** 4 vCPU / 6 GB RAM limits leading to OOM crashes during training or heavy computation.
- **Remediation:** Absolutely no ML training on the live VPS. Run training locally or on GitHub Action runners, deploying only serialized weight binaries.

### 4. API Budget Runaway
- **Risk:** Unrestricted LLM queries (especially DeepSeek V4 or R1 calls) exhausting funds.
- **Remediation:** Enforce the daily budget guard ($3.00 USD hard limit). Keep prompt payloads small by limiting DB queries (e.g. news query limit <= 15).
