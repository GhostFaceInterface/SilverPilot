import sys
from datetime import datetime, UTC, timedelta
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append("/Users/boe747/SilverPilot/apps/api")

from app.core.db import Base
from app.core.config import Settings
from app.collectors.public_sources import collect_global_xag_usd

# Setup in-memory sqlite for debugging
engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

db = SessionLocal()

observed_at = datetime.now(UTC) - timedelta(minutes=1)
observed_timestamp = int(observed_at.timestamp())

yahoo_json = {
    "chart": {
        "result": [
            {
                "meta": {"symbol": "SI=F", "currency": "USD"},
                "timestamp": [observed_timestamp],
                "indicators": {
                    "quote": [{"close": [28.45], "open": [28.40], "high": [28.50], "low": [28.35], "volume": [1000]}]
                },
            }
        ],
        "error": None,
    }
}


def handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=yahoo_json)


client = httpx.Client(transport=httpx.MockTransport(handler))

try:
    # First seed assets since XAG is needed
    from app.models import Asset

    xag = Asset(symbol="XAG", name="Silver Spot", asset_type="metal", is_active=True)
    db.add(xag)
    db.commit()

    # Pass the priority override to include yahoo-si-f
    run, raw_inserted, snapshot = collect_global_xag_usd(
        db, settings=Settings(global_xag_source_priority="yahoo-si-f"), client=client
    )
    print("RUN STATUS:", run.status)
    print("ERROR MESSAGE:", run.error_message)
    print("DETAILS:", run.details_json)
except Exception as e:
    print("EXCEPTION:", e)
finally:
    client.close()
    db.close()
