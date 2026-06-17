from fastapi import APIRouter, FastAPI

from silverpilot.app.core.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(title=resolved_settings.app_name)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok", "app": resolved_settings.app_name}

    api_v1 = APIRouter(prefix="/api/v1")

    @api_v1.get("/health", tags=["health"])
    def api_health() -> dict[str, str]:
        return {"status": "ok", "app": resolved_settings.app_name}

    app.include_router(api_v1)
    return app


app = create_app()
