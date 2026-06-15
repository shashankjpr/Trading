from pathlib import Path

from HistoricalData.Storage.duckdb_tools import DB_FILE, query_bars, connect


def get_bars(
    ticker: str,
    timeframe: str = "1m",
    start: str | None = None,
    end: str | None = None,
    limit: int | None = None,
    db_file: Path = DB_FILE,
):
    conn = connect(db_file)
    df = query_bars(conn, ticker=ticker, timeframe=timeframe, start=start, end=end, limit=limit)
    conn.close()
    return df


if __name__ == "__main__":
    # Example usage
    print("Querying AAPL 5-minute bars from the DuckDB file:")
    df = get_bars("AAPL", timeframe="5m", start="2025-06-01", end="2025-06-02", limit=10)
    print(df)
