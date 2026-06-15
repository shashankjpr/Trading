"""
Hourly Inflection Levels Calculator
Mirrors Pine Script: "Hourly Inflection Levels - 1 Month"
Identifies pivot-based support/resistance levels with touch counting and zone clustering.
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass

ROOT_DIR = Path(__file__).resolve().parents[3]
DB_PATH = ROOT_DIR / "HistoricalData" / "Storage" / "trading_data.duckdb"


@dataclass
class PivotLevel:
    """Single inflection level with metadata."""
    price: float
    level_type: str  # 'PH' (pivot high), 'PL' (pivot low), 'BPH' (body PH), 'BPL' (body PL)
    intensity: float  # displacement % between pivot and opposite extreme
    touches: int  # count of times this level was touched/tested
    first_seen_idx: int  # bar index where first detected
    last_touch_idx: int  # bar index where last touched


@dataclass
class PivotZone:
    """Grouped levels (resistance zone or support zone)."""
    level_type: str
    price_min: float
    price_max: float
    price_center: float
    levels: List[PivotLevel]  # all levels in this zone


class InflectionLevelsCalculator:
    """
    Calculates hourly inflection levels from OHLC data.
    Matches Pine Script logic for pivot detection, intensity calculation, touch counting,
    and zone clustering.
    """

    def __init__(
        self,
        lookback_days: int = 30,
        left_bars: int = 5,
        right_bars: int = 5,
        min_touches: int = 2,
        min_intensity_pct: float = 0.30,
        merge_tol_pct: float = 0.30,
        zone_tol_pct: float = 0.80,
    ):
        """
        Args:
            lookback_days: Historical bars to analyze (days).
            left_bars: Bars to the left of pivot to check for higher/lower.
            right_bars: Bars to the right of pivot to check for higher/lower.
            min_touches: Minimum touch count to qualify a level.
            min_intensity_pct: Minimum displacement (%) between pivot and opposite extreme.
            merge_tol_pct: Tolerance (%) for merging nearby levels.
            zone_tol_pct: Tolerance (%) for grouping levels into zones.
        """
        self.lookback_days = lookback_days
        self.left_bars = left_bars
        self.right_bars = right_bars
        self.min_touches = min_touches
        self.min_intensity_pct = min_intensity_pct
        self.merge_tol_pct = merge_tol_pct
        self.zone_tol_pct = zone_tol_pct

        self.win_len = left_bars + right_bars + 1

    def detect_pivot_highs(self, highs: np.ndarray) -> np.ndarray:
        """Detect pivot highs: high[i] > high[i-left:i] and high[i] > high[i+1:i+right+1]."""
        n = len(highs)
        pivots = np.full(n, np.nan)
        for i in range(self.left_bars, n - self.right_bars):
            if (
                highs[i] > np.max(highs[i - self.left_bars : i])
                and highs[i] > np.max(highs[i + 1 : i + self.right_bars + 1])
            ):
                pivots[i] = highs[i]
        return pivots

    def detect_pivot_lows(self, lows: np.ndarray) -> np.ndarray:
        """Detect pivot lows: low[i] < low[i-left:i] and low[i] < low[i+1:i+right+1]."""
        n = len(lows)
        pivots = np.full(n, np.nan)
        for i in range(self.left_bars, n - self.right_bars):
            if (
                lows[i] < np.min(lows[i - self.left_bars : i])
                and lows[i] < np.min(lows[i + 1 : i + self.right_bars + 1])
            ):
                pivots[i] = lows[i]
        return pivots

    def calculate_intensity(self, pivot_idx: int, highs: np.ndarray, lows: np.ndarray, is_high: bool) -> float:
        """
        Calculate inflection intensity.
        For pivot high: (pivot - lowest_in_window) / pivot * 100
        For pivot low: (highest_in_window - pivot) / pivot * 100
        """
        start = max(0, pivot_idx - self.left_bars)
        end = min(len(highs), pivot_idx + self.right_bars + 1)

        if is_high:
            pivot = highs[pivot_idx]
            opposite = np.min(lows[start:end])
            intensity = (pivot - opposite) / pivot * 100 if pivot != 0 else 0
        else:
            pivot = lows[pivot_idx]
            opposite = np.max(highs[start:end])
            intensity = (opposite - pivot) / pivot * 100 if pivot != 0 else 0

        return intensity

    def merge_nearby_levels(self, prices: List[Tuple[float, int]], tolerance_pct: float) -> List[Tuple[float, int]]:
        """
        Merge levels within tolerance (%) of each other.
        Returns merged prices with accumulated touch counts.
        """
        if not prices:
            return []

        sorted_prices = sorted(prices, key=lambda x: x[0])
        merged = []
        current_group = [sorted_prices[0]]

        for i in range(1, len(sorted_prices)):
            price, count = sorted_prices[i]
            ref_price = current_group[0][0]
            pct_diff = abs(price - ref_price) / ref_price * 100

            if pct_diff <= tolerance_pct:
                current_group.append((price, count))
            else:
                avg_price = np.mean([p[0] for p in current_group])
                total_count = sum(p[1] for p in current_group)
                merged.append((avg_price, total_count))
                current_group = [(price, count)]

        if current_group:
            avg_price = np.mean([p[0] for p in current_group])
            total_count = sum(p[1] for p in current_group)
            merged.append((avg_price, total_count))

        return merged

    def cluster_into_zones(self, prices: List[float], tolerance_pct: float) -> List[Tuple[float, float, List[float]]]:
        """
        Cluster prices into zones within tolerance (%).
        Returns list of (zone_min, zone_max, prices_in_zone).
        """
        if len(prices) <= 1:
            return [(p, p, [p]) for p in prices]

        sorted_prices = sorted(prices)
        zones = []
        cluster_prices = [sorted_prices[0]]
        cluster_min = sorted_prices[0]

        for i in range(1, len(sorted_prices)):
            price = sorted_prices[i]
            pct_diff = (price - cluster_prices[-1]) / cluster_prices[-1] * 100

            if pct_diff <= tolerance_pct:
                cluster_prices.append(price)
            else:
                if len(cluster_prices) >= 1:
                    zones.append((min(cluster_prices), max(cluster_prices), cluster_prices.copy()))
                cluster_prices = [price]

        if cluster_prices:
            zones.append((min(cluster_prices), max(cluster_prices), cluster_prices.copy()))

        return zones

    def analyze(self, df: pd.DataFrame) -> Dict[str, List[PivotLevel]]:
        """
        Analyze hourly OHLC data and return identified levels.

        Args:
            df: DataFrame with columns [timestamp, open, high, low, close].
               Index should be consecutive hourly bars.

        Returns:
            Dict with keys 'PH', 'PL', 'BPH', 'BPL', each containing list of PivotLevel objects.
        """
        if df.empty or len(df) < self.win_len:
            return {"PH": [], "PL": [], "BPH": [], "BPL": []}

        highs = df["high"].values
        lows = df["low"].values
        opens = df["open"].values
        closes = df["close"].values

        # Detect pivots
        ph_pivots = self.detect_pivot_highs(highs)
        pl_pivots = self.detect_pivot_lows(lows)
        bph_pivots = self.detect_pivot_highs(np.maximum(opens, closes))
        bpl_pivots = self.detect_pivot_lows(np.minimum(opens, closes))

        # Collect pivot data: (price, intensity, index)
        ph_data = []
        pl_data = []
        bph_data = []
        bpl_data = []

        for i in range(len(df)):
            if not np.isnan(ph_pivots[i]):
                intensity = self.calculate_intensity(i, highs, lows, is_high=True)
                if intensity >= self.min_intensity_pct:
                    ph_data.append((ph_pivots[i], intensity, i))

            if not np.isnan(pl_pivots[i]):
                intensity = self.calculate_intensity(i, highs, lows, is_high=False)
                if intensity >= self.min_intensity_pct:
                    pl_data.append((pl_pivots[i], intensity, i))

            if not np.isnan(bph_pivots[i]):
                body_high = max(opens[i], closes[i])
                body_low = min(opens[i], closes[i])
                lows_window = np.minimum(opens, closes)
                intensity = (body_high - np.min(lows_window[max(0, i - self.left_bars) : i + self.right_bars + 1])) / body_high * 100 if body_high != 0 else 0
                if intensity >= self.min_intensity_pct:
                    bph_data.append((body_high, intensity, i))

            if not np.isnan(bpl_pivots[i]):
                body_low = min(opens[i], closes[i])
                body_high = max(opens[i], closes[i])
                highs_window = np.maximum(opens, closes)
                intensity = (np.max(highs_window[max(0, i - self.left_bars) : i + self.right_bars + 1]) - body_low) / body_low * 100 if body_low != 0 else 0
                if intensity >= self.min_intensity_pct:
                    bpl_data.append((body_low, intensity, i))

        # Merge and count touches
        def process_pivots(data: List[Tuple[float, float, int]], level_type: str) -> List[PivotLevel]:
            if not data:
                return []

            # Group by price within tolerance
            price_groups = {}
            for price, intensity, idx in data:
                found_group = False
                for key in price_groups:
                    if abs(price - key) / key * 100 <= self.merge_tol_pct:
                        price_groups[key].append((price, intensity, idx))
                        found_group = True
                        break
                if not found_group:
                    price_groups[price] = [(price, intensity, idx)]

            # Create PivotLevel objects
            levels = []
            for prices_in_group in price_groups.values():
                # Select the level with max intensity from the cluster
                max_intensity_idx = np.argmax([p[1] for p in prices_in_group])
                max_intensity_level = prices_in_group[max_intensity_idx]
                selected_price = max_intensity_level[0]
                selected_intensity = max_intensity_level[1]
                touches = len(prices_in_group)
                first_idx = min(p[2] for p in prices_in_group)
                last_idx = max(p[2] for p in prices_in_group)

                if touches >= self.min_touches:
                    levels.append(
                        PivotLevel(
                            price=selected_price,
                            level_type=level_type,
                            intensity=selected_intensity,
                            touches=touches,
                            first_seen_idx=first_idx,
                            last_touch_idx=last_idx,
                        )
                    )

            return sorted(levels, key=lambda x: x.price)

        return {
            "PH": process_pivots(ph_data, "PH"),
            "PL": process_pivots(pl_data, "PL"),
            "BPH": process_pivots(bph_data, "BPH"),
            "BPL": process_pivots(bpl_data, "BPL"),
        }

    def cluster_levels(self, levels: List[PivotLevel]) -> List[PivotZone]:
        """
        Cluster levels into zones.
        Returns PivotZone objects for visualization and analysis.
        """
        if not levels:
            return []

        sorted_levels = sorted(levels, key=lambda x: x.price)
        zones = []
        cluster = [sorted_levels[0]]

        for i in range(1, len(sorted_levels)):
            level = sorted_levels[i]
            prev_price = cluster[-1].price

            if abs(level.price - prev_price) / prev_price * 100 <= self.zone_tol_pct:
                cluster.append(level)
            else:
                if len(cluster) >= 1:
                    prices = [l.price for l in cluster]
                    zone = PivotZone(
                        level_type=cluster[0].level_type,
                        price_min=min(prices),
                        price_max=max(prices),
                        price_center=np.mean(prices),
                        levels=cluster.copy(),
                    )
                    zones.append(zone)
                cluster = [level]

        if cluster:
            prices = [l.price for l in cluster]
            zone = PivotZone(
                level_type=cluster[0].level_type,
                price_min=min(prices),
                price_max=max(prices),
                price_center=np.mean(prices),
                levels=cluster,
            )
            zones.append(zone)

        return zones
