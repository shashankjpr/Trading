import duckdb

conn = duckdb.connect('trading_data.duckdb')
print('Distinct tickers (top 50):')
print(conn.execute('SELECT ticker, count(*) as cnt FROM stock_bars_1m GROUP BY ticker ORDER BY cnt DESC LIMIT 50').df())
print('\nUNKNOWN count:')
print(conn.execute("SELECT count(*) as c FROM stock_bars_1m WHERE ticker='UNKNOWN'").fetchone())
conn.close()
