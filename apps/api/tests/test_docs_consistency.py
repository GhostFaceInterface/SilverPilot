from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_phase_plan_is_the_only_phase_authority():
    phase_plan = _read("docs/PHASE_PLAN.md")

    assert "single canonical phase and status artifact" in phase_plan
    assert "Phase 5 re-baseline" in phase_plan


def test_readme_declares_non_canonical_phase_status():
    readme = _read("README.md")

    assert "non-canonical for phase status" in readme
    assert "docs/PHASE_PLAN.md" in readme
    assert "Current official phase is" not in readme


def test_plan_archive_points_back_to_phase_plan():
    plan = _read("PLAN.md")

    assert "not a" in plan
    assert "canonical source for current SilverPilot phase status" in plan
    assert "docs/PHASE_PLAN.md" in plan


def test_roadmap_is_archival_not_canonical():
    roadmap = _read("docs/ROADMAP.md")

    assert "This file is archival only." in roadmap
    assert "intentionally non-canonical" in roadmap
    assert "canonical delivery roadmap" not in roadmap


def test_worklog_is_evidence_only():
    worklog = _read("docs/WORKLOG.md")

    assert "dated evidence and smoke/deploy history only" in worklog
    assert "Historical entries may contain superseded phase claims." in worklog
    assert "docs/PHASE_PLAN.md" in worklog
