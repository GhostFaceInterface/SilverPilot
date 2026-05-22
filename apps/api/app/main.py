import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.routes import router
from app.core.config import get_settings

# Configure structured logging for silverpilot loggers
logging.basicConfig(level=logging.INFO)
silverpilot_logger = logging.getLogger("silverpilot")
silverpilot_logger.setLevel(logging.INFO)
if not silverpilot_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    silverpilot_logger.addHandler(handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    polling_task = None

    if settings.telegram_bot_token:
        if settings.telegram_bot_mode == "polling":
            from app.agents.telegram_bot import start_polling

            polling_task = asyncio.create_task(start_polling())
        elif settings.telegram_bot_mode == "webhook":
            from app.agents.telegram_bot import set_telegram_webhook

            asyncio.create_task(set_telegram_webhook())

    yield

    if polling_task:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()
