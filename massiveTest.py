from massive import RESTClient

# Initialize the client with your API key
client = RESTClient("KPypXbmeTqe0eSQx5n55L2pRM7gpE0d8")

aggs = []
# Get 1-day aggregates for AAPL from Jan 2026 to Jan 2026
for a in client.list_aggs(
    ticker="AAPL",
    multiplier=1,
    timespan="day",
    from_="2026-01-01",
    to="2026-01-05",
    limit=50000,
):
    aggs.append(a)

print(f"Retrieved {len(aggs)} records.")

