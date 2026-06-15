import importlib.util
import json
import os
import time
from datetime import date, timedelta
from pathlib import Path

from massive import RESTClient

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT_DIR / "HistoricalData" / "Storage" / "TickerListConfig.py"
CACHE_DIR = ROOT_DIR / "HistoricalData" / "Storage" / "cache"
TIME_GRANULARITY = "minute"

API_KEY = os.getenv("MASSIVE_API_KEY")
if not API_KEY:
    raise EnvironmentError(
        "Please set MASSIVE_API_KEY in your environment before running this script.\n"
        "Example (PowerShell): $env:MASSIVE_API_KEY = 'your_api_key'"
    )

client = RESTClient(API_KEY)


def load_config(path: Path):
    spec = importlib.util.spec_from_file_location("ticker_config", str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load config from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def agg_to_dict(agg):
    if hasattr(agg, "to_dict"):
        data = agg.to_dict()
    elif hasattr(agg, "__dict__"):
        data = {k: v for k, v in agg.__dict__.items() if not k.startswith("_")}
    else:
        try:
            data = dict(agg)
        except Exception:
            data = {"value": str(agg)}

    def convert(value):
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value

    return {k: convert(v) for k, v in data.items()}


def cache_file_path(ticker: str, start_date: date, end_date: date) -> Path:
    return CACHE_DIR / f"{ticker}_{start_date:%Y%m%d}_{end_date:%Y%m%d}_{TIME_GRANULARITY}.json"


def ensure_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_cached_data(ticker: str, start_date: date, end_date: date):
    path = cache_file_path(ticker, start_date, end_date)
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_cached_data(ticker: str, start_date: date, end_date: date, data):
    path = cache_file_path(ticker, start_date, end_date)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Saved {len(data)} bars to cache: {path}")


def get_date_range(days: int):
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    return start_date, end_date


def fetch_bars(ticker: str, from_date: date, to_date: date):
    bars = []
    for agg in client.list_aggs(
        ticker=ticker,
        multiplier=1,
        timespan=TIME_GRANULARITY,
        from_=from_date.isoformat(),
        to=to_date.isoformat(),
        limit=50000,
    ):
        bars.append(agg_to_dict(agg))
    return bars


def fetch_year_data(ticker: str, start_date: date, end_date: date):
    data = []
    current_start = start_date
    api_call_count = 0
    while current_start < end_date:
        current_end = min(current_start + timedelta(days=30), end_date)
        print(f"Fetching {ticker} from {current_start} to {current_end} ...")
        chunk = fetch_bars(ticker, current_start, current_end)
        data.extend(chunk)
        api_call_count += 1
        
        # Rate limiting: 5 API calls per minute = 1 call every 12 seconds
        if current_end < end_date:
            print(f"Rate limit: waiting 20 seconds before next API call...")
            time.sleep(20)
        
        if current_end >= end_date:
            break
        current_start = current_end + timedelta(days=1)
    return data


def main():
    config = load_config(CONFIG_PATH)
    tickers = getattr(config, "TICKERS", ["AAPL"])
    days = getattr(config, "LOOKBACK_DAYS", 365)
    ensure_cache_dir()
    start_date, end_date = get_date_range(days)

    print(f"Ticker list: {tickers}")
    print(f"Retrieving {TIME_GRANULARITY} data from {start_date} to {end_date} ({days} days).")

    for ticker in tickers:
        cached = load_cached_data(ticker, start_date, end_date)
        if cached is not None:
            print(f"Loaded cached data for {ticker}: {len(cached)} bars")
            continue

        bars = fetch_year_data(ticker, start_date, end_date)
        if not bars:
            print(f"No bars retrieved for {ticker}.")
            continue

        save_cached_data(ticker, start_date, end_date, bars)


if __name__ == "__main__":
    main()
