#!/usr/bin/env python3
"""Verify SilverPilot Codex agent/skill framework wiring."""

from __future__ import annotations

import pathlib
import sys
import tomllib


ROOT = pathlib.Path(__file__).resolve().parents[2]
AGENTS_DIR = ROOT / ".codex" / "agents"
SKILLS_DIR = ROOT / ".codex" / "skills"
WORKFLOWS_DIR = ROOT / ".codex" / "workflows"
MEMORY_DIR = ROOT / ".codex" / "memory"

REQUIRED_AGENT_KEYS = {
    "name",
    "description",
    "developer_instructions",
}

EXPECTED_SKILLS = {
    "architect": {
        "fastapi-sqlalchemy",
        "financial-agent-runtime",
        "deployment-safety",
    },
    "ci_investigator": {"github-actions-monitoring"},
    "db_investigator": {"fastapi-sqlalchemy", "alembic-migrations"},
    "deploy_guardian": {
        "deployment-safety",
        "docker-compose-ops",
        "alembic-migrations",
    },
    "deployment_investigator": {"deployment-safety", "docker-compose-ops"},
    "final_reviewer": {
        "git-safe-operations",
        "deployment-safety",
        "pytest-fastapi",
        "integration-testing",
    },
    "git_guardian": {"git-safe-operations"},
    "implementation_worker": set(),
    "post_deploy_monitor": {
        "deployment-safety",
        "github-actions-monitoring",
        "integration-testing",
    },
    "rollback_planner": {"deployment-safety", "alembic-migrations"},
    "scout": {"financial-agent-runtime"},
    "security_reviewer": {
        "git-safe-operations",
        "github-actions-monitoring",
        "financial-agent-runtime",
    },
    "test_strategist": {
        "pytest-fastapi",
        "integration-testing",
        "financial-risk-regression",
        "docker-compose-ops",
    },
    "test_verifier": {
        "pytest-fastapi",
        "integration-testing",
        "docker-compose-ops",
        "financial-risk-regression",
    },
    "troubleshooter": set(),
}

EXPECTED_SKILL_FILES = {
    "alembic-migrations",
    "collector-data-pipeline",
    "deployment-safety",
    "docker-compose-ops",
    "documentation-consistency",
    "fastapi-sqlalchemy",
    "financial-agent-runtime",
    "financial-risk-regression",
    "github-actions-monitoring",
    "integration-testing",
    "llm-observability-budget",
    "ml-backtest-dataset",
    "pytest-fastapi",
    "streamlit-dashboard",
}

EXPECTED_WORKFLOWS = {
    "codegraph-maintenance.md",
    "collector-pipeline-validation.md",
    "context-handoff.md",
    "docs-consistency.md",
    "runtime-agent-safety-audit.md",
}

SCOUT_HANDOFF_AGENTS = {
    "architect",
    "db_investigator",
    "implementation_worker",
    "security_reviewer",
    "test_strategist",
    "troubleshooter",
}

EXPECTED_MODEL_POLICY = {
    "scout": {"model": "gpt-5.4-mini", "model_reasoning_effort": "medium"},
    "db_investigator": {"model": "gpt-5.4-mini", "model_reasoning_effort": "medium"},
    "test_verifier": {
        "model": "gpt-5.4-mini",
        "model_reasoning_effort": "medium",
    },
}


def main() -> int:
    errors: list[str] = []
    agent_files = sorted(AGENTS_DIR.glob("*.toml"))
    seen_agents: set[str] = set()

    for skill in EXPECTED_SKILL_FILES:
        skill_path = SKILLS_DIR / skill / "SKILL.md"
        if not skill_path.is_file():
            errors.append(f"Missing expected skill file {skill_path}")

    for workflow in EXPECTED_WORKFLOWS:
        workflow_path = WORKFLOWS_DIR / workflow
        if not workflow_path.is_file():
            errors.append(f"Missing expected workflow file {workflow_path}")

    codegraph_path = MEMORY_DIR / "codegraph.md"
    if not codegraph_path.is_file():
        errors.append(f"Missing local codegraph memory {codegraph_path}")

    if not agent_files:
        errors.append(f"No agent TOML files found under {AGENTS_DIR}")

    for path in agent_files:
        try:
            data = tomllib.loads(path.read_text())
        except tomllib.TOMLDecodeError as exc:
            errors.append(f"{path}: invalid TOML: {exc}")
            continue

        missing_keys = REQUIRED_AGENT_KEYS - data.keys()
        if missing_keys:
            errors.append(f"{path}: missing keys {sorted(missing_keys)}")
            continue

        name = data["name"]
        seen_agents.add(name)
        instructions = data["developer_instructions"]

        for phrase in ("Skill preflight", "Clarification gate", "Loaded skills"):
            if phrase not in instructions:
                errors.append(f"{path}: missing required phrase {phrase!r}")

        if name == "scout":
            for phrase in (
                "Scout mode",
                "RTK evidence",
                "Files searched",
                "Ranges read",
                "Do not reread",
                "Next agent",
            ):
                if phrase not in instructions:
                    errors.append(f"{path}: missing scout handoff output field {phrase!r}")

        if name in SCOUT_HANDOFF_AGENTS:
            for phrase in ("scout handoff", "context-handoff"):
                if phrase not in instructions:
                    errors.append(f"{path}: missing scout handoff requirement phrase {phrase!r}")

        for skill in EXPECTED_SKILLS.get(name, set()):
            skill_path = SKILLS_DIR / skill / "SKILL.md"
            if not skill_path.is_file():
                errors.append(f"{path}: missing skill file {skill_path}")
            if skill not in instructions:
                errors.append(f"{path}: does not mention required skill {skill!r}")

        expected_model = EXPECTED_MODEL_POLICY.get(name)
        if expected_model:
            for key, expected_value in expected_model.items():
                actual_value = data.get(key)
                if actual_value != expected_value:
                    errors.append(f"{path}: expected {key}={expected_value!r}, got {actual_value!r}")

    missing_agents = set(EXPECTED_SKILLS) - seen_agents
    if missing_agents:
        errors.append(f"Missing agent definitions: {sorted(missing_agents)}")

    extra_agents = seen_agents - set(EXPECTED_SKILLS)
    if extra_agents:
        errors.append(f"Unexpected agent definitions: {sorted(extra_agents)}")

    if errors:
        print("Agent framework verification FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Agent framework verification PASSED ({len(agent_files)} agents)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
