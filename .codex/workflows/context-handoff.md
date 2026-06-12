# Context Handoff Workflow

Use this workflow whenever `scout` hands repository evidence to another Codex
agent or back to the main context. The goal is concise, reusable context rather
than raw dumps.

## Required Fields

Every scout handoff includes:

- `Loaded skills`: exact local skills read, or `none` with a short reason.
- `Scout mode`: `micro-scout` or `full-scout`.
- `RTK evidence`: short path/line/fact bullets proving the map.
- `Files searched`: `rg` queries or file lists used.
- `Ranges read`: path plus line ranges inspected.
- `Do not reread`: paths/ranges already summarized unless the file changes.
- `Relevant files`: likely implementation, test, config, or doc targets.
- `Confirmed facts`: evidence-backed facts only.
- `Missing evidence`: unresolved items that could change scope or risk.
- `Next agent`: recommended specialist, implementer, verifier, or `main context`.

## Compression Rule

For long work and context compaction, carry only compact path/line/fact/risk
summaries. Do not paste raw logs, full files, broad diffs, or unfiltered command
output into the handoff.

## Plugin Note

The `context-management` plugin may speed up save/restore, but it is not a
policy authority. If the plugin is unavailable or too broad, use this format
manually.
