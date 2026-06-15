#!/usr/bin/env python3
"""
Quick start examples for Hourly Inflection Levels analyzer.
Run these from the Trading directory root.
"""

import sys
from pathlib import Path

# Example 1: Analyze AAPL with default settings and save chart
print("\n=== Example 1: Basic analysis for AAPL ===\n")
print("Command:")
print("  cd Analysis/HourlyLevels")
print("  python analyze.py AAPL --output ../results/aapl.png\n")

# Example 2: Analyze multiple tickers and export levels
print("=== Example 2: Batch analysis ===\n")
print("Bash script:")
print("""
for ticker in AAPL TSLA MSFT SPY QQQ; do
  python analyze.py $ticker \\
    --lookback-days 60 \\
    --output ../results/${ticker}_60d.png \\
    --export-levels ../results/${ticker}_levels.csv
done
""")

# Example 3: Python API usage
print("\n=== Example 3: Python API usage ===\n")
print("""
from HistoricalData.Storage.duckdb_tools import connect, query_bars
from Analysis.HourlyLevels.inflection_levels import InflectionLevelsCalculator
from Analysis.HourlyLevels.visualizer import LevelsVisualizer

# Load data
conn = connect()
df = query_bars(conn, ticker='NVDA', timeframe='1h', limit=500)
conn.close()

# Calculate levels
calc = InflectionLevelsCalculator(
    lookback_days=60,
    left_bars=7,
    right_bars=7,
    min_touches=3,
    min_intensity_pct=0.50,
)

levels = calc.analyze(df)
zones = {lt: calc.cluster_levels(levels[lt]) for lt in ['PH', 'PL', 'BPH', 'BPL']}

# Visualize
viz = LevelsVisualizer()
fig = viz.plot(df, levels, zones, show_volume=True)
viz.save(fig, 'nvda_analysis.png')

# Get strongest resistance levels
strong_resistance = [l for l in levels['PH'] if l.touches >= 3]
for level in sorted(strong_resistance, key=lambda x: x.price, reverse=True):
    print(f"Resistance: {level.price:.2f} ({level.touches}x, {level.intensity:.2f}%)")
""")

# Example 4: Advanced options
print("\n=== Example 4: Advanced options ===\n")
print("""
python analyze.py SPY \\
  --lookback-days 90 \\
  --left-bars 10 \\
  --right-bars 10 \\
  --min-touches 4 \\
  --min-intensity 1.00 \\
  --merge-tolerance 0.15 \\
  --zone-tolerance 0.50 \\
  --output results/spy_advanced.png \\
  --show-volume \\
  --export-levels results/spy_levels.csv
""")

print("\n=== Documentation ===\n")
print("Full docs and parameter explanations: Analysis/HourlyLevels/README.md\n")
print("Get command help:\n  python analyze.py --help\n")
