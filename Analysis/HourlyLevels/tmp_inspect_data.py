from HistoricalData.Storage.duckdb_tools import connect, query_bars

conn = connect()
for tf in ['1m', '5m', '1h', '1d']:
    try:
        df = query_bars(conn, 'AAPL', timeframe=tf, limit=5)
        if len(df):
            print(tf, len(df), df['timestamp'].iloc[0], df['timestamp'].iloc[-1])
        else:
            print(tf, 0, 'none', 'none')
    except Exception as e:
        print('ERR', tf, e)
conn.close()
