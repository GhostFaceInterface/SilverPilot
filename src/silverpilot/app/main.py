from fastapi import FastAPI

from silverpilot.app.api import api_router
from silverpilot.app.api.schemas import HealthResponse
from silverpilot.app.core.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(title=resolved_settings.app_name)

    @app.get(
        "/health", response_model=HealthResponse, response_model_exclude_none=True, tags=["health"]
    )
    def health() -> HealthResponse:
        return HealthResponse(status="ok", app=resolved_settings.app_name)

    app.include_router(api_router)
    return app


app = create_app()
