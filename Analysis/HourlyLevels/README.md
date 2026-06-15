# Hourly Inflection Levels Analyzer

Python implementation of the Pine Script "Hourly Inflection Levels - 1 Month" indicator.

Identifies hourly pivot-based support/resistance levels with:
- **Pivot Detection**: Automatic identification of pivot highs/lows and body pivots
- **Inflection Intensity**: Measures displacement between pivot and opposite extreme
- **Touch Counting**: Aggregates nearby pivots and counts how many times levels are tested
- **Zone Clustering**: Groups adjacent levels into support/resistance zones
- **Visualization**: Matplotlib charts with candlesticks, levels, zones, and labels

## Features

- Analyzes hourly OHLC data from DuckDB
- Detects 4 pivot types: Wick High/Low, Body High/Low
- Configurable pivot windows, intensity thresholds, and merging tolerances
- Exports levels to CSV for further analysis
- High-quality candlestick charts with zone shading and touch labels

## Installation

Ensure you have the required packages:

```bash
pip install pandas numpy matplotlib duckdb
```

## Usage

### Basic Analysis (Display Chart)

```bash
cd c:\Users\shash\Desktop\Trading\Analysis\HourlyLevels
python analyze.py AAPL
```

### Save Chart to File

```bash
python analyze.py TSLA --output results/tsla_levels.png
```

### Adjust Parameters

```bash
python analyze.py NVDA \
  --lookback-days 30 \
  --left-bars 5 \
  --right-bars 5 \
  --min-touches 1 \
  --min-intensity 2.0 \
  --merge-tolerance 0.7 \
  --zone-tolerance 0.15
```

### Export Identified Levels to CSV

```bash
python analyze.py SPY --export-levels results/spy_levels.csv
```

### Full Options

```
usage: analyze.py [-h] [--lookback-days LOOKBACK_DAYS] [--left-bars LEFT_BARS] 
                  [--right-bars RIGHT_BARS] [--min-touches MIN_TOUCHES] 
                  [--min-intensity MIN_INTENSITY] [--merge-tolerance MERGE_TOLERANCE] 
                  [--zone-tolerance ZONE_TOLERANCE] [--output OUTPUT] 
                  [--show-volume] [--no-zones] [--no-labels] 
                  [--export-levels EXPORT_LEVELS]
                  ticker

positional arguments:
  ticker                Stock ticker symbol (e.g., AAPL, TSLA)

optional arguments:
  -h, --help            Show help message
  --lookback-days       Historical lookback in days (default: 30)
  --left-bars           Pivot left bars (default: 5)
  --right-bars          Pivot right bars (default: 5)
  --min-touches         Minimum touch count (default: 1)
  --min-intensity       Min intensity %% (default: 2.0)
  --merge-tolerance     Merge tolerance %% (default: 0.7)
  --zone-tolerance      Zone tolerance %% (default: 0.15)
  --output              Output file path for chart (e.g., chart.png)
  --show-volume         Include volume subplot
  --no-zones            Hide zone shading
  --no-labels           Hide price labels
  --export-levels       Export levels to CSV
```

## Python API

```python
import pandas as pd
from HistoricalData.Storage.duckdb_tools import connect, query_bars
from Analysis.HourlyLevels.inflection_levels import InflectionLevelsCalculator
from Analysis.HourlyLevels.visualizer import LevelsVisualizer

# Load hourly data from DuckDB
conn = connect()
df = query_bars(conn, ticker='AAPL', timeframe='1h', limit=500)
conn.close()

# Analyze
calc = InflectionLevelsCalculator(
    lookback_days=30,
    left_bars=5,
    right_bars=5,
    min_touches=1,
    min_intensity_pct=2.0,
    merge_tol_pct=0.7,
    zone_tol_pct=0.15,
)

levels_by_type = calc.analyze(df)  # Returns {' PH': [...], 'PL': [...], 'BPH': [...], 'BPL': [...]}

# Get all PH levels with 3+ touches
strong_resistance = [l for l in levels_by_type['PH'] if l.touches >= 3]

# Cluster into zones
zones_by_type = {}
for level_type in ['PH', 'PL', 'BPH', 'BPL']:
    zones_by_type[level_type] = calc.cluster_levels(levels_by_type[level_type])

# Visualize
viz = LevelsVisualizer()
fig = viz.plot(df, levels_by_type, zones_by_type)
viz.save(fig, 'output.png')
```

## Algorithm Summary

1. **Pivot Detection**
   - Pivot High: Bar where high > all bars to the left AND right within window
   - Pivot Low: Bar where low < all bars to the left AND right within window
   - Body Pivots: Same logic but using max(open, close) and min(open, close)

2. **Inflection Intensity**
   - For pivot high: `(pivot - lowest_in_window) / pivot * 100`
   - For pivot low: `(highest_in_window - pivot) / pivot * 100`
   - Filters out weak pivots with low intensity

3. **Touch Counting & Merging**
   - Nearby pivots (within merge tolerance) are grouped
   - Touch count = number of pivots in group
   - Only levels with touches ≥ min_touches are qualified

4. **Zone Clustering**
   - Qualified levels are sorted by price
   - Adjacent levels within zone tolerance are grouped
   - Each group becomes a zone (support/resistance band)

5. **Visualization**
   - Candlestick chart with OHLC bars
   - Solid lines for resistance (PH/BPH), dashed for support (PL/BPL)
   - Shaded zones show clustered level areas
   - Labels show price, touch count, and intensity percentage

## Output Interpretation

- **PH (Pivot High)**: Wick-based resistance; solid red line
- **PL (Pivot Low)**: Wick-based support; dashed teal line
- **BPH (Body Pivot High)**: Close/open-based resistance; solid orange line
- **BPL (Body Pivot Low)**: Close/open-based support; dashed light teal line
- **Zones**: Shaded regions where multiple levels cluster; stronger reaction zones
- **Touches**: How many pivot points test this level (higher = stronger level)
- **Intensity**: Strength of price rejection at the pivot; higher % = stronger rejection

## Example Results

```
Hourly Inflection Levels Analyzer
======================================================================
Ticker: AAPL
Lookback: 30 days
Pivot Window: left=5, right=5
Minimum touches: 2
Min intensity: 0.30%
Merge tolerance: 0.30%
Zone tolerance: 0.80%

Loaded 720 hourly bars from 2026-05-10 00:00:00 to 2026-06-09 00:00:00

Analyzing pivots and inflection levels...

Detected Levels:
----------------------------------------------------------------------

Pivot High (Wick Resistance): 5 levels
   234.50  |  Touches: 3x  |  Intensity:  2.45%
   235.20  |  Touches: 2x  |  Intensity:  1.89%
   ...

Zones (grouped levels):
----------------------------------------------------------------------

Pivot High Zone: 2 zones
  233.50 - 235.80  |  Center: 234.65  |  Levels: 3
  ...

Generating visualization...
Chart saved to results/aapl_levels.png
```

## Notes

- Data must be loaded from DuckDB first (use `HistoricalData/Storage/duckdb_tools.py`)
- Requires hourly OHLC bars; works on any chart timeframe by requesting 1h security
- Pivot detection needs at least `left_bars + right_bars + 1` bars of history
- Small timeframes (5m, 15m) may show more noise; use hourly+ for clearer levels
- Adjust `--min-intensity` higher for only the strongest rejections
- Increase `--merge-tolerance` to combine nearby levels; decrease for granularity

## References

- Original Pine Script: "Hourly Inflection Levels - 1 Month"
- Pivot analysis concepts from technical analysis literature
- Zone clustering inspired by market profile/volume profile analysis
