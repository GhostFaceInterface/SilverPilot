Implement only the minimal fix from the approved diagnosis.

Constraints:
- Do not refactor unrelated files.
- Do not touch `.agent/`.
- Do not create or touch root `/agents`; runtime agent definitions live under `apps/api/app/agents/` unless the approved plan explicitly says otherwise.
- Do not change database schema unless explicitly approved.
- Keep the patch reversible.

After changes:
- Run the smallest meaningful verification.
- Summarize changed files.
- Explain remaining risk.
