# Docker Compose & VPS Operations Skill

Use this manual when adjusting Docker Compose setups, updating configurations, or managing remote VPS operations.

## 🔒 VPS Port Hardening & Security

- **Loopback Interface Binding:** Database ports (default `5433`) and internal API ports (`8000`) must be bound exclusively to the loopback interface (`127.0.0.1`) on the VPS to prevent external intrusion:
  ```yaml
  ports:
    - "127.0.0.1:5433:5432"
  ```
- **Zero-Trust Network Gate:** Only the Streamlit Dashboard (port `8501`) or configured Nginx proxies should be publicly exposed. All communication between the dashboard and API runs internally over the Docker bridge network.

---

## 🛠️ Remote Deployment Rules

- **No Direct VPS Patches:** Direct editing of code on the remote VPS is forbidden. Always implement, test, and commit locally first, then execute a deployment script (`./scripts/deploy.sh`) to push changes, pull them on the VPS, and run validation.
- **Environment Variable Sync:** When adding new configuration parameters or tokens (like `AGENT_API_TOKEN`), ensure they are correctly added to `.env` locally and manually updated in `/opt/silverpilot/SilverPilot/.env.production` on the VPS.
- **Resource Constraints:** The production VPS is restricted (e.g. 4 vCPU, 6 GB RAM). No heavy ML training cycles may be executed on the VPS. ML models must be trained off-VPS, with only weight binaries pushed to the repository.
