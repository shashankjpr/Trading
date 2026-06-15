import argparse
import importlib.util
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import duckdb
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
DB_FILE = ROOT_DIR / "HistoricalData" / "Storage" / "trading_data.duckdb"
TICKER_CONFIG_PATH = ROOT_DIR / "HistoricalData" / "Storage" / "TickerListConfig.py"
CACHE_DIR = ROOT_DIR / "HistoricalData" / "Storage" / "cache"

BASE_TABLE = "stock_bars_1m"
TIMEFRAME_VIEWS = {
    "1m": BASE_TABLE,
    "5m": "stock_bars_5m",
    "1h": "stock_bars_1h",
    "1d": "stock_bars_1d",
}

REQUIRED_COLUMNS = [
    "ticker",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
    "transactions",
]


def load_config(path: Path) -> object:
    spec = importlib.util.spec_from_file_location("ticker_config", str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load config from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def connect(db_path: Path = DB_FILE) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    conn.execute("PRAGMA threads=4")
    return conn


def initialize_database(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {BASE_TABLE} (
            ticker VARCHAR,
            timestamp TIMESTAMP,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume BIGINT,
            vwap DOUBLE,
            transactions BIGINT
        );
        """
    )

    try:
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{BASE_TABLE}_ticker_time "
            f"ON {BASE_TABLE} (ticker, timestamp);"
        )
    except duckdb.Error:
        # Some DuckDB versions do not support IF NOT EXISTS on indexes.
        try:
            conn.execute(
                f"CREATE INDEX idx_{BASE_TABLE}_ticker_time ON {BASE_TABLE} (ticker, timestamp);"
            )
        except duckdb.Error:
            pass

    conn.execute(
        """
        CREATE OR REPLACE VIEW stock_bars_5m AS
        SELECT
            ticker,
            TIMESTAMP 'epoch' + (FLOOR(EXTRACT(epoch FROM timestamp) / 300) * 300) * INTERVAL '1 second' AS timestamp,
            MIN_BY(open, timestamp) AS open,
            MAX(high) AS high,
            MIN(low) AS low,
            MAX_BY(close, timestamp) AS close,
            SUM(volume) AS volume,
            SUM(vwap * volume) / NULLIF(SUM(volume), 0) AS vwap,
            SUM(transactions) AS transactions
        FROM stock_bars_1m
        GROUP BY ticker, 2;
        """
    )

    conn.execute(
        """
        CREATE OR REPLACE VIEW stock_bars_1h AS
        SELECT
            ticker,
            DATE_TRUNC('hour', timestamp) AS timestamp,
            MIN_BY(open, timestamp) AS open,
            MAX(high) AS high,
            MIN(low) AS low,
            MAX_BY(close, timestamp) AS close,
            SUM(volume) AS volume,
            SUM(vwap * volume) / NULLIF(SUM(volume), 0) AS vwap,
            SUM(transactions) AS transactions
        FROM stock_bars_1m
        GROUP BY ticker, 2;
        """
    )

    conn.execute(
        """
        CREATE OR REPLACE VIEW stock_bars_1d AS
        SELECT
            ticker,
            DATE_TRUNC('day', timestamp) AS timestamp,
            MIN_BY(open, timestamp) AS open,
            MAX(high) AS high,
            MIN(low) AS low,
            MAX_BY(close, timestamp) AS close,
            SUM(volume) AS volume,
            SUM(vwap * volume) / NULLIF(SUM(volume), 0) AS vwap,
            SUM(transactions) AS transactions
        FROM stock_bars_1m
        GROUP BY ticker, 2;
        """
    )

    print(f"Initialized DuckDB schema and views in {DB_FILE}")


def normalize_timestamp(series: pd.Series) -> pd.Series:
    if pd.api.types.is_integer_dtype(series.dtype) or pd.api.types.is_float_dtype(series.dtype):
        return pd.to_datetime(series, unit="ms", errors="coerce")
    return pd.to_datetime(series, unit="ms", errors="coerce")


def normalize_records(records: List[Dict]) -> pd.DataFrame:
    df = pd.DataFrame(records)
    if df.empty:
        return df

    if "ticker" not in df.columns:
        df["ticker"] = None

    df["timestamp"] = normalize_timestamp(df["timestamp"])
    # Ensure required columns exist (fill missing with NA)
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    df = df[REQUIRED_COLUMNS].copy()

    # Coerce timestamp already handled; coerce numeric columns safely
    float_cols = ["open", "high", "low", "close", "vwap"]
    int_cols = ["volume", "transactions"]

    for col in float_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

    for col in int_cols:
        # Convert to numeric, coerce errors to NaN, then convert to pandas nullable Int64
        df[col] = pd.to_numeric(df[col], errors="coerce")
        # If values are floats representing integers (e.g., 123.0), round safely before casting
        df[col] = df[col].where(df[col].isna(), df[col].round(0))
        df[col] = df[col].astype("Int64")

    # Keep `ticker` as nullable string; do not fill here so caller can supply defaults
    df["ticker"] = df["ticker"].astype("string")

    # Do not drop rows here - defer dropping/duplicate removal to loader after default ticker fill
    return df


def load_json_file(path: Path, default_ticker: Optional[str] = None) -> pd.DataFrame:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, dict):
        if "results" in payload and isinstance(payload["results"], list):
            records = payload["results"]
        elif "data" in payload and isinstance(payload["data"], list):
            records = payload["data"]
        else:
            records = [payload]
    elif isinstance(payload, list):
        records = payload
    else:
        raise ValueError(f"Unsupported JSON payload type: {type(payload)}")

    df = normalize_records(records)
    if df.empty:
        return df

    if default_ticker is not None and "ticker" in df.columns:
        df["ticker"] = df["ticker"].fillna(default_ticker)

    # Final cleaning: drop rows missing essential keys and remove duplicates
    df = df.dropna(subset=["ticker", "timestamp"])
    df = df.drop_duplicates(subset=["ticker", "timestamp"], keep="last")

    return df


def ingest_dataframe(conn: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    conn.register("new_bars", df)
    # Ensure any leftover temp table is removed before creating a new one
    try:
        conn.execute("DROP TABLE IF EXISTS tmp_bars")
    except Exception:
        # Some duckdb builds may require DROP TABLE OR REPLACE; ignore failures
        pass
    conn.execute("CREATE TEMP TABLE tmp_bars AS SELECT * FROM new_bars")

    try:
        conn.execute(
            f"INSERT OR REPLACE INTO {BASE_TABLE} SELECT * FROM tmp_bars"
        )
    except duckdb.Error:
        conn.execute(
            f"MERGE INTO {BASE_TABLE} AS target "
            "USING tmp_bars AS source "
            "ON target.ticker = source.ticker AND target.timestamp = source.timestamp "
            "WHEN MATCHED THEN UPDATE SET "
            "open = source.open, high = source.high, low = source.low, close = source.close, "
            "volume = source.volume, vwap = source.vwap, transactions = source.transactions "
            "WHEN NOT MATCHED THEN INSERT (ticker,timestamp,open,high,low,close,volume,vwap,transactions) "
            "VALUES (source.ticker, source.timestamp, source.open, source.high, source.low, source.close, source.volume, source.vwap, source.transactions);"
        )

    return len(df)


def ingest_cache_files(
    conn: duckdb.DuckDBPyConnection,
    tickers: Optional[Iterable[str]] = None,
    cache_dir: Path = CACHE_DIR,
) -> int:
    tickers = list(tickers) if tickers is not None else []
    if not tickers:
        config = load_config(TICKER_CONFIG_PATH)
        tickers = getattr(config, "TICKERS", [])

    if not tickers:
        raise ValueError("No tickers provided and no tickers found in config.")

    cache_dir.mkdir(parents=True, exist_ok=True)
    total_rows = 0
    for ticker in tickers:
        pattern = f"{ticker}_*_minute.json"
        files = sorted(cache_dir.glob(pattern))
        if not files:
            print(f"Warning: no cache files found for {ticker} in {cache_dir}")
            continue

        for path in files:
            df = load_json_file(path, default_ticker=ticker)
            rows = ingest_dataframe(conn, df)
            if rows:
                print(f"Ingested {rows} rows from {path.name}")
            total_rows += rows

    return total_rows


def get_view_name(timeframe: str) -> str:
    timeframe = timeframe.lower()
    if timeframe not in TIMEFRAME_VIEWS:
        raise ValueError(f"Timeframe must be one of {list(TIMEFRAME_VIEWS)}")
    return TIMEFRAME_VIEWS[timeframe]


def query_bars(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    timeframe: str = "1m",
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    view = get_view_name(timeframe)
    sql = [f"SELECT * FROM {view} WHERE ticker = ?"]
    params = [ticker]
    if start:
        sql.append("AND timestamp >= ?")
        params.append(start)
    if end:
        sql.append("AND timestamp <= ?")
        params.append(end)
    sql.append("ORDER BY timestamp ASC")
    if limit is not None:
        sql.append(f"LIMIT {limit}")
    query = " \n".join(sql)
    return conn.execute(query, params).df()


def query_latest_timestamp(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    timeframe: str = "1m",
) -> Optional[pd.Timestamp]:
    view = get_view_name(timeframe)
    result = conn.execute(
        f"SELECT MAX(timestamp) AS max_ts FROM {view} WHERE ticker = ?",
        [ticker],
    ).fetchone()
    if result is None or result[0] is None:
        return None
    return pd.to_datetime(result[0])


def show_sample(conn: duckdb.DuckDBPyConnection, ticker: str) -> None:
    for timeframe in ["1m", "5m", "1h", "1d"]:
        df = query_bars(conn, ticker, timeframe=timeframe, limit=5)
        print(f"\n=== {ticker} {timeframe} sample ===")
        print(df)


def main() -> None:
    parser = argparse.ArgumentParser(description="DuckDB storage and retrieval for stock bar JSON data.")
    parser.add_argument("--db-file", default=DB_FILE, help="DuckDB file path")
    parser.add_argument("--command", choices=["init", "ingest", "sample", "query"], required=True)
    parser.add_argument("--ticker", help="Ticker symbol for ingest/sample/query")
    parser.add_argument("--timeframe", default="1m", help="Timeframe: 1m, 5m, 1h, 1d")
    parser.add_argument("--start", help="Start timestamp (ISO format or yyyy-mm-dd)")
    parser.add_argument("--end", help="End timestamp (ISO format or yyyy-mm-dd)")
    parser.add_argument("--limit", type=int, help="Limit rows returned")
    args = parser.parse_args()

    conn = connect(Path(args.db_file))
    if args.command == "init":
        initialize_database(conn)
        print("Database initialized.")
    elif args.command == "ingest":
        initialize_database(conn)
        config = load_config(TICKER_CONFIG_PATH)
        tickers = getattr(config, "TICKERS", [])
        rows = ingest_cache_files(conn, tickers=tickers)
        print(f"Total ingested rows: {rows}")
    elif args.command == "sample":
        if not args.ticker:
            raise ValueError("--ticker is required for sample")
        print(f"Sample rows for {args.ticker}")
        show_sample(conn, args.ticker)
    elif args.command == "query":
        if not args.ticker:
            raise ValueError("--ticker is required for query")
        df = query_bars(conn, args.ticker, timeframe=args.timeframe, start=args.start, end=args.end, limit=args.limit)
        print(df)
    conn.close()


if __name__ == "__main__":
    main()
