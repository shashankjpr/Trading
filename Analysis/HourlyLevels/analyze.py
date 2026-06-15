"""
Hourly Inflection Levels: Main runner script.
Load hourly OHLC from DuckDB, analyze for pivot levels, and visualize.
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

# Add parent dirs to path for imports
# Path structure: Trading/Analysis/HourlyLevels/analyze.py
# parents[2] = Trading root directory
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from HistoricalData.Storage.duckdb_tools import connect, query_bars, query_latest_timestamp
from Analysis.HourlyLevels.inflection_levels import InflectionLevelsCalculator
from Analysis.HourlyLevels.visualizer import LevelsVisualizer


def main():
    parser = argparse.ArgumentParser(
        description="Analyze hourly inflection levels from DuckDB stock data."
    )
    parser.add_argument("ticker", help="Stock ticker symbol (e.g., AAPL, TSLA)")
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=30,
        help="Historical lookback period in days (default: 30)",
    )
    parser.add_argument(
        "--left-bars",
        type=int,
        default=5,
        help="Pivot left bars for detection (default: 5)",
    )
    parser.add_argument(
        "--right-bars",
        type=int,
        default=5,
        help="Pivot right bars for detection (default: 5)",
    )
    parser.add_argument(
        "--min-touches",
        type=int,
        default=1,
        help="Minimum touch count to qualify a level (default: 1)",
    )
    parser.add_argument(
        "--min-intensity",
        type=float,
        default=2.0,
        help="Min inflection intensity in %% (default: 2.0)",
    )
    parser.add_argument(
        "--merge-tolerance",
        type=float,
        default=0.7,
        help="Merge tolerance for nearby levels in %% (default: 0.7)",
    )
    parser.add_argument(
        "--zone-tolerance",
        type=float,
        default=0.15,
        help="Zone clustering tolerance in %% (default: 0.15)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path for chart (e.g., chart.png). If omitted, displays interactively.",
    )
    parser.add_argument(
        "--show-volume",
        action="store_true",
        help="Include volume subplot in visualization.",
    )
    parser.add_argument(
        "--no-zones",
        action="store_true",
        help="Hide zone shading in chart.",
    )
    parser.add_argument(
        "--no-labels",
        action="store_true",
        help="Hide price labels with touch counts and intensity.",
    )
    parser.add_argument(
        "--export-levels",
        type=str,
        default=None,
        help="Export identified levels to CSV file.",
    )
    parser.add_argument(
        "--minute-latest-day",
        action="store_true",
        help="Display 1-minute bars for the latest day while keeping levels from the hourly analysis.",
    )

    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f"Hourly Inflection Levels Analyzer")
    print(f"{'='*70}")
    print(f"Ticker: {args.ticker}")
    print(f"Lookback: {args.lookback_days} days")
    print(f"Pivot Window: left={args.left_bars}, right={args.right_bars}")
    print(f"Minimum touches: {args.min_touches}")
    print(f"Min intensity: {args.min_intensity}%")
    print(f"Merge tolerance: {args.merge_tolerance}%")
    print(f"Zone tolerance: {args.zone_tolerance}%")
    print()

    # Connect to DuckDB and load hourly data
    try:
        conn = connect()
        print(f"Loading hourly data for {args.ticker}...")
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=args.lookback_days)
        
        df = query_bars(
            conn,
            ticker=args.ticker,
            timeframe="1h",
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            limit=None,
        )

        minute_df = None
        if args.minute_latest_day:
            print(f"Loading 1-minute data for latest day display for {args.ticker}...")
            latest_minute_ts = query_latest_timestamp(conn, args.ticker, timeframe="1m")
            if latest_minute_ts is None:
                print("WARNING: No 1-minute data exists for this ticker; falling back to hourly display.")
            else:
                minute_end = latest_minute_ts
                minute_start = minute_end - timedelta(days=1)
                minute_df = query_bars(
                    conn,
                    ticker=args.ticker,
                    timeframe="1m",
                    start=minute_start.isoformat(),
                    end=minute_end.isoformat(),
                    limit=None,
                )
                if minute_df.empty:
                    print("WARNING: No 1-minute bars found for the latest available day; falling back to hourly display.")
                    minute_df = None
                else:
                    print(f"Loaded {len(minute_df)} minute bars from {minute_df.iloc[0]['timestamp']} to {minute_df.iloc[-1]['timestamp']}")

        conn.close()

        if df.empty:
            print(f"ERROR: No hourly data found for {args.ticker}.")
            return 1

        print(f"Loaded {len(df)} hourly bars from {df.iloc[0]['timestamp']} to {df.iloc[-1]['timestamp']}")
        print()

        # Initialize calculator
        calc = InflectionLevelsCalculator(
            lookback_days=args.lookback_days,
            left_bars=args.left_bars,
            right_bars=args.right_bars,
            min_touches=args.min_touches,
            min_intensity_pct=args.min_intensity,
            merge_tol_pct=args.merge_tolerance,
            zone_tol_pct=args.zone_tolerance,
        )

        # Analyze
        print("Analyzing pivots and inflection levels...")
        levels_by_type = calc.analyze(df)

        # Summary
        print()
        print("Detected Levels:")
        print("-" * 70)
        for level_type in ["PH", "PL", "BPH", "BPL"]:
            levels = levels_by_type[level_type]
            if levels:
                label = {
                    "PH": "Pivot High (Wick Resistance)",
                    "PL": "Pivot Low (Wick Support)",
                    "BPH": "Body Pivot High",
                    "BPL": "Body Pivot Low",
                }[level_type]
                print(f"\n{label}: {len(levels)} levels")
                for level in levels:
                    print(
                        f"  {level.price:>8.2f}  |  Touches: {level.touches}x  |  "
                        f"Intensity: {level.intensity:>6.2f}%"
                    )

        # Cluster into zones
        print("\n" + "-" * 70)
        print("Zones (grouped levels):")
        print("-" * 70)
        zones_by_type = {}
        for level_type in ["PH", "PL", "BPH", "BPL"]:
            zones = calc.cluster_levels(levels_by_type[level_type])
            zones_by_type[level_type] = zones
            if zones:
                label = {
                    "PH": "Pivot High Zone",
                    "PL": "Pivot Low Zone",
                    "BPH": "Body Pivot High Zone",
                    "BPL": "Body Pivot Low Zone",
                }[level_type]
                print(f"\n{label}: {len(zones)} zones")
                for zone in zones:
                    print(
                        f"  {zone.price_min:>8.2f} - {zone.price_max:>8.2f}  |  "
                        f"Center: {zone.price_center:>8.2f}  |  Levels: {len(zone.levels)}"
                    )

        # Export levels to CSV if requested
        if args.export_levels:
            print(f"\n" + "-" * 70)
            export_path = Path(args.export_levels)
            export_path.parent.mkdir(parents=True, exist_ok=True)

            rows = []
            for level_type in ["PH", "PL", "BPH", "BPL"]:
                for level in levels_by_type[level_type]:
                    rows.append({
                        "level_type": level.level_type,
                        "price": level.price,
                        "touches": level.touches,
                        "intensity_pct": level.intensity,
                        "first_seen_idx": level.first_seen_idx,
                        "last_touch_idx": level.last_touch_idx,
                    })

            export_df = pd.DataFrame(rows)
            export_df.to_csv(export_path, index=False)
            print(f"Levels exported to {export_path}")

        # Visualize
        print(f"\n" + "-" * 70)
        print("Generating visualization...")
        visualizer = LevelsVisualizer(figsize=(16, 8))

        plot_df = df
        title = f"{args.ticker} - Hourly Inflection Levels ({args.lookback_days}d lookback)"
        if minute_df is not None:
            plot_df = minute_df
            title = f"{args.ticker} - Latest Day 1m Price with Hourly Inflection Levels"

        fig = visualizer.plot(
            plot_df,
            levels_by_type,
            zones_by_type,
            title=title,
            show_volume=args.show_volume,
            show_zones=not args.no_zones,
            show_labels=not args.no_labels,
        )

        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            visualizer.save(fig, str(output_path))
        else:
            print("Displaying chart...")
            visualizer.show(fig)

        print("\n" + "=" * 70)
        print("Analysis complete!")
        print("=" * 70 + "\n")
        return 0

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
