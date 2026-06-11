# Lint and Validate Skill

## 1. Purpose
Formalizes lightweight developer checks and quality validation gates before code changes are committed or proposed. Verifies code style, type annotations, configuration structures, environment variables, and runs the local test suite to ensure robust and regression-free development in the SilverPilot project.

## 2. Rules
- **Pre-commit Validation:** Never declare a task or phase "done" without executing the relevant local validation command or tests.
- **No Production Side-effects:** Validation commands must run in dry-run, mock, or local test environments. Do not modify production configurations or trigger external API mutations.
- **Clean Output:** Pay close attention to warnings, type-checking diagnostics, and linting notices. Resolve or document them rather than ignoring them.

## 3. Recommended Patterns
1. **Lightweight Syntax Check:** Run basic parser and syntax checks on updated files using standard python interpreter checks or quick linters if available (e.g., `.venv/bin/python -m py_compile <file_path>`).
2. **Strict Type Annotations:** Ensure new functions and classes have explicit Python type annotations (e.g., using `typing` or modern generic types).
3. **Configuration Check:** Verify that any updates to `.env`, `config.py`, or config dictionaries strictly adhere to existing schemas and include default fallback values.
4. **Targeted Test Execution:** Instead of running the entire slow test suite for a minor change, isolate and run the specific test module or case that targets the modified code (e.g., `.venv/bin/python -m pytest apps/api/tests/test_specific.py`).

## 4. Anti-Patterns
- **Assuming it Works:** Declaring a file edit successful based solely on the absence of compiler errors, without running the actual test suite.
- **Leaking Test State:** Writing unit tests that write to persistent/production databases or rely on live external services without mock interfaces.
- **Hardcoding Environment Variables:** Hardcoding path roots, database URIs, or token structures instead of querying them from the environment or settings.

## 5. Checklist
- [ ] Have all modified or new files been checked for syntax correctness?
- [ ] Are type annotations present for all newly defined function signatures and classes?
- [ ] Have environment variables or config keys been validated against schema constraints?
- [ ] Did you run the specific test suite (e.g., `pytest`) locally and verify it passed with 0 errors?
- [ ] Are all mock configurations completely isolated from production and local databases?

## 6. Example Guidance
When implementing a new indicator utility `app/utils/indicators.py`:
1. **Local Syntax Check:** Run `.venv/bin/python -m py_compile app/utils/indicators.py` to confirm syntax.
2. **Verify Type Annotations:** Ensure function signatures look like `def calculate_rsi(prices: list[float], period: int = 14) -> list[float]:` instead of unannotated arguments.
3. **Execute Relevant Tests:** Run `.venv/bin/python -m pytest apps/api/tests/test_indicators.py` to verify that calculations match mathematical expectations.
4. **Environment Isolation:** Do not hardcode testing constants inside the production modules. Use `settings` or `config` references.
