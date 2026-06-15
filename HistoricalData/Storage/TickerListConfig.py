"""
Ticker list configuration for the retrieval workflow.

Add the tickers you want to track here.
"""

TICKERS = [
    "AAPL",
    "AMD",
    "NVDA",
    "QQQ",
    # "SPX",
    "SPY",
    "TSLA",
    "PLTR",
    "MSFT",
    "AMZN",
    "INTC",
    "GOOGL"
]

# Retrieval defaults
TIME_GRANULARITY = "minute"  # 1-minute bars
LOOKBACK_DAYS = 365  # 365 days of history from today
