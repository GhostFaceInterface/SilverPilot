import httpx
import json
from decimal import Decimal
from datetime import datetime, UTC


def parse_yahoo_finance_chart_json(
    raw_payload: str,
    *,
    fetched_at: datetime,
    expected_symbol: str,
    source: str,
    parser_version: str,
):
    try:
        body = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        print("PARSE_ERROR: JSONDecodeError")
        raise exc

    chart = body.get("chart") or {}
    error = chart.get("error")
    if error:
        print(f"chart error: {error}")
        return

    result_list = chart.get("result")
    if not isinstance(result_list, list) or not result_list:
        print("PARSE_ERROR: result missing")
        return

    result = result_list[0]
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quotes = indicators.get("quote") or []

    if not quotes or not isinstance(quotes, list):
        print("PARSE_ERROR: quote missing")
        return

    quote = quotes[0] or {}
    closes = quote.get("close") or []

    if len(timestamps) != len(closes):
        print(f"PARSE_ERROR: length mismatch timestamps={len(timestamps)}, closes={len(closes)}")
        return

    # Find the last non-null close price
    idx = len(closes) - 1
    price = None
    observed_timestamp = None
    while idx >= 0:
        if closes[idx] is not None:
            try:
                price = Decimal(str(closes[idx]))
                observed_timestamp = timestamps[idx]
                break
            except Exception:
                pass
        idx -= 1

    if price is None or observed_timestamp is None:
        print("PARSE_ERROR: no valid close prices")
        return

    observed_at = datetime.fromtimestamp(observed_timestamp, tz=UTC)
    print(f"Success! Price: {price}, Observed at: {observed_at}")


url = "https://query1.finance.yahoo.com/v8/finance/chart/SI=F?range=5d&interval=5m"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}
r = httpx.get(url, headers=headers)
print(f"Status: {r.status_code}")
parse_yahoo_finance_chart_json(
    r.text, fetched_at=datetime.now(UTC), expected_symbol="SI=F", source="yahoo-si-f", parser_version="1.0"
)
