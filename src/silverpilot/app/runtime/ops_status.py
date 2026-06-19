import argparse
import json
from collections.abc import Sequence

from sqlalchemy.orm import Session

from silverpilot.app.core.settings import get_settings
from silverpilot.app.db.session import create_db_engine
from silverpilot.app.runtime.health import SystemHealthService


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print SilverPilot system health JSON.")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args(argv)
    settings = get_settings()
    engine = create_db_engine(args.database_url)
    with Session(engine) as session:
        snapshot = SystemHealthService(session=session, settings=settings).snapshot()
    print(json.dumps(snapshot.payload, sort_keys=True, default=str))
    return 0 if snapshot.status != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
