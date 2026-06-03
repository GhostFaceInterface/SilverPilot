Implement only the minimal fix from the approved diagnosis.

Constraints:
- Do not refactor unrelated files.
- Do not touch `.agent/`.
- Do not touch root `/agents` runtime definitions unless the approved plan explicitly says so.
- Do not change database schema unless explicitly approved.
- Keep the patch reversible.

After changes:
- Run the smallest meaningful verification.
- Summarize changed files.
- Explain remaining risk.
