# Streamlit Dashboard Development Skill

Use this manual when editing the Streamlit application or building new dashboard pages.

## 📊 Premium Aesthetics & Layouts

- Favors high contrast, clean boundaries, and sharp edges.
- Avoids cliché purple or default Streamlit styles. Customize with custom CSS injection where required.
- Organizes complex dashboards using responsive tabs (`st.tabs`).

---

## 📈 Headless Matplotlib Chart Rendering

To prevent window-manager crashes in Docker containers or headless VPS deployments, you must configure Matplotlib to use the `Agg` backend **before** importing `pyplot`:

```python
import matplotlib
matplotlib.use("Agg")  # Must be declared first!
import matplotlib.pyplot as plt
```

---

## 🔒 Port Isolation & Zero-Trust Access

- Streamlit code must **never** connect directly to the database. All interactions must proceed through public or private FastAPI HTTP endpoints.
- Ensure the `X-Agent-Token` header containing `AGENT_API_TOKEN` is passed when making requests to secure `/agent/*` REST endpoints.
- Store token values securely in environment configurations, never hardcoded in dashboard scripts.
