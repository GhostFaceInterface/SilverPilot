from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_builds_backend_runtime_as_non_root_user() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "FROM python:3.12-slim" in dockerfile
    assert "python -m pip install ." in dockerfile
    assert "USER silverpilot" in dockerfile
    assert 'silverpilot.app.main:app", "--host", "0.0.0.0", "--port", "8000"' in dockerfile


def test_compose_defines_api_migration_postgres_and_collector_boundaries() -> None:
    compose = (ROOT / "docker-compose.yml").read_text()

    assert "postgres:" in compose
    assert "migrate:" in compose
    assert "api:" in compose
    assert "worker:" in compose
    assert "collector:" in compose
    assert "telegram:" in compose
    assert '"127.0.0.1:${SILVERPILOT_API_PORT:-8000}:8000"' in compose
    assert '"127.0.0.1:${SILVERPILOT_POSTGRES_PORT:-5432}:5432"' in compose
    assert '"alembic", "upgrade", "head"' in compose
    assert '"silverpilot-paper-loop"' in compose
    assert 'profiles: ["telegram"]' in compose
    assert 'profiles: ["collector"]' in compose
    assert "service_completed_successfully" in compose
    assert "dashboard:" not in compose


def test_env_example_documents_runtime_without_secret_values() -> None:
    env_example = (ROOT / ".env.example").read_text()

    assert (
        "SILVERPILOT_DATABASE_URL=postgresql+psycopg://silverpilot:change-me@postgres:5432/silverpilot"
        in env_example
    )
    assert "POSTGRES_PASSWORD=change-me" in env_example
    assert "SILVERPILOT_TELEGRAM_ENABLED=false" in env_example
    assert "SILVERPILOT_TELEGRAM_BOT_TOKEN=" in env_example
    assert "SILVERPILOT_RUNTIME_ENABLED=false" in env_example
    assert "SILVERPILOT_RUNTIME_WARMUP_BARS=201" in env_example
    assert (
        "SILVERPILOT_COLLECTOR_BANK_INSTRUMENT_ID=00000000-0000-0000-0000-000000000000"
        in env_example
    )


def test_deployment_runbook_keeps_remote_deploy_approval_gated() -> None:
    runbook = (ROOT / "docs" / "deployment.md").read_text()

    assert "ssh silverpilot-vps" in runbook
    assert "explicit user approval" in runbook
    assert "pytest -q" in runbook
    assert "bash .codex/scripts/verify-docker.sh" in runbook
    assert "silverpilot-bootstrap-paper" in runbook
    assert "/api/v1/system/health" in runbook
    assert "Rollback requires" in runbook
    assert "Do not print `.env` contents or secret values." in runbook


def test_vps_deploy_workflow_is_manual_and_environment_gated() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy-vps.yml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "environment: production" in workflow
    assert "secrets.VPS_HOST" in workflow
    assert "secrets.VPS_PORT" in workflow
    assert "secrets.VPS_PROJECT_PATH" in workflow
    assert "secrets.VPS_SSH_KEY" in workflow
    assert "secrets.VPS_USER" in workflow
    assert 'git checkout --detach "$DEPLOY_SHA"' in workflow
    assert "docker compose build" in workflow
    assert "docker compose run --rm migrate" in workflow
    assert "/api/v1/system/health" in workflow
