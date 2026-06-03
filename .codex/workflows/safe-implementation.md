# Safe Implementation Workflow

Use this workflow when executing code changes, fixing bugs, or implementing new endpoints.

## 🚀 Step 1: Pre-Coding Scan
- Identify the target file using the `scout` agent.
- Read relevant skill sheets (e.g., `fastapi-sqlalchemy.md` or `testing-verification.md`).
- Formulate a clear, minimal change strategy.

## 🛠️ Step 2: Implementation
- Apply minimal edits using targeted file replace tools.
- Never refactor unrelated files.
- Preserve existing comments, docstrings, and logic boundaries.

## 🧪 Step 3: Lint & Formatting Check
- Verify style constraints before staging.
- Ensure the Ruff format runs correctly without errors:
  ```bash
  ruff format path/to/changed_file.py
  ruff check --fix path/to/changed_file.py
  ```

## 🔍 Step 4: Local Test Verification
- Execute `pytest` targeting only the affected test suite:
  ```bash
  pytest apps/api/tests/test_filename.py
  ```
- Confirm zero failures and verify mock coverage to ensure no socket connections are leaking to live APIs.
- Run the full test suite once before declaring the implementation phase done.
