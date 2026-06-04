---
name: "docker-compose-ops"
description: "Codex-local skill bundle for Docker Compose validation, local image builds, VPS constraints, and container safety."
---

# Docker Compose Ops

This is a Codex-local skill bundle, not a guaranteed auto-discovered official Codex skill.

## Use When
- Dockerfile, Compose, profile, volume, healthcheck, env, port, or deployment-adjacent behavior changes.

## Rules
- `docker compose config` is the minimum validation.
- Build only affected images unless shared base behavior changed.
- Local `docker compose up` is runtime verification, not deployment.
- Do not run remote deploys or production service restarts without explicit user approval.
- Never print `.env` contents or secret values.
- Database and internal API ports should remain loopback-bound where exposed to the host.

## Commands
```bash
bash .codex/scripts/verify-docker.sh
bash .codex/scripts/verify-docker.sh --build
```

`--build` requires a running local Docker daemon. If unavailable, classify Docker build verification as UNKNOWN/SKIPPED.
