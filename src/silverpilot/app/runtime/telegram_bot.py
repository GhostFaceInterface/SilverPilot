import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from time import sleep
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from silverpilot.app.core.settings import Settings, get_settings
from silverpilot.app.db.models import TelegramBotStateModel
from silverpilot.app.db.session import create_db_engine
from silverpilot.app.runtime.health import SystemHealthService


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the read-only Telegram bot status worker.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", default=30.0, type=float)
    args = parser.parse_args(argv)
    settings = get_settings()
    engine = create_db_engine(args.database_url)
    while True:
        output = _tick(engine=engine, settings=settings)
        print(json.dumps(output, sort_keys=True))
        if args.once:
            return 0
        sleep(args.interval_seconds)


def _tick(*, engine: Engine, settings: Settings) -> dict[str, object]:
    now = datetime.now(UTC)
    with Session(engine) as session:
        state = _state(session, now)
        if not settings.telegram_enabled or not settings.telegram_bot_token:
            state.status = "disabled"
            state.last_error = None
        else:
            state.status = "polling"
            health = SystemHealthService(session=session, settings=settings).snapshot()
            state.last_error = None if health.status != "failed" else "system health failed"
        state.updated_at = now
        session.commit()
        return {
            "bot_name": state.bot_name,
            "status": state.status,
            "last_update_id": state.last_update_id,
            "read_only_commands": ["/health", "/prices", "/portfolio", "/trades", "/risk", "/help"],
        }


def _state(session: Session, now: datetime) -> TelegramBotStateModel:
    state = session.scalar(
        select(TelegramBotStateModel).where(TelegramBotStateModel.bot_name == "silverpilot")
    )
    if state is not None:
        return state
    state = TelegramBotStateModel(
        id=uuid4(),
        bot_name="silverpilot",
        status="disabled",
        created_at=now,
    )
    session.add(state)
    session.flush()
    return state


if __name__ == "__main__":
    raise SystemExit(main())
