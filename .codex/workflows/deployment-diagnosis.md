# Deployment Diagnosis & Monitoring Workflow

Use this workflow when deployment fails on the VPS, docker-compose services do not start, or VPS smoke test triggers find errors.

## 📋 Intake & Context Check
Verify active VPS environment mappings:
1. Is `.env.production` on the VPS synchronized with local settings (e.g. matching `AGENT_API_TOKEN` and job selections)?
2. Are all containers running via loopback constraints (`127.0.0.1`)?

---

## 🛠️ Step-by-Step Diagnosis

### 1. Check Container Status
Verify running docker services:
```bash
docker-compose ps
```

### 2. Inspect Container Logs
Target logs for the failing container (e.g. `api`, `dashboard`, `postgres`):
```bash
docker-compose logs --tail=100 -f <service_name>
```

### 3. Verify Local Port Isolation
Ensure database port `5433` and api port `8000` are bound to local host interface `127.0.0.1` and not exposed to the public internet:
```bash
netstat -tulpn | grep -E "5433|8000"
```

### 4. Running VPS Smoke Tests
Execute the VPS-specific deployment smoke validation:
```bash
./scripts/vps_smoke.sh
```
Check if database migrations are up to date and E2E pipelines pass cleanly.
