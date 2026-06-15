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
        min_touches: int = 1,
        min_intensity_pct: float = 3.0,
        min_tol_pct: float = 0.12,
        auto_intensity: bool = True,
    ):
        """
        Args:
            lookback_days: Historical bars to analyze (days).
            left_bars: Bars to the left of pivot to check for higher/lower.
            right_bars: Bars to the right of pivot to check for higher/lower.
            min_touches: Minimum touch count to qualify a zone.
            min_intensity_pct: Minimum displacement (%) between pivot and opposite extreme.
            min_tol_pct: Tolerance (%) for merging nearby pivot prices into a zone.
            auto_intensity: If True, use ATR% to determine intensity threshold.
        """
        self.lookback_days = lookback_days
        self.left_bars = left_bars
        self.right_bars = right_bars
        self.min_touches = min_touches
        self.min_intensity_pct = min_intensity_pct
        self.min_tol_pct = min_tol_pct
        self.auto_intensity = auto_intensity

        self.win_len = left_bars + right_bars + 1

    def compute_atr_percent(self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> float:
        """Compute ATR% using a 14-period ATR on hourly bars."""
        if len(highs) < 15:
            return float("nan")

        prev_closes = np.concatenate(([np.nan], closes[:-1]))
        true_range = np.maximum.reduce(
            [highs - lows, np.abs(highs - prev_closes), np.abs(lows - prev_closes)]
        )
        true_range[0] = np.nan

        tr_series = pd.Series(true_range)
        atr14 = tr_series.rolling(14, min_periods=14).mean().to_numpy()
        last_atr = atr14[-1]
        if np.isnan(last_atr) or closes[-1] == 0:
            return float("nan")

        return last_atr / closes[-1] * 100

    def effective_intensity_threshold(self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> float:
        """Return the active intensity threshold based on ATR% or manual setting."""
        if not self.auto_intensity:
            return self.min_intensity_pct

        atr_pct = self.compute_atr_percent(highs, lows, closes)
        if np.isnan(atr_pct):
            return self.min_intensity_pct

        if atr_pct > 6.0:
            return 10.0
        if atr_pct >= 3.0:
            return 6.0
        return 3.0

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
            intensity = (pivot - opposite) / pivot * 100 if pivot != 0 else 0.0
        else:
            pivot = lows[pivot_idx]
            opposite = np.max(highs[start:end])
            intensity = (opposite - pivot) / pivot * 100 if pivot != 0 else 0.0

        return intensity

    def analyze(self, df: pd.DataFrame) -> Dict[str, List[PivotLevel]]:
        """
        Analyze hourly OHLC data and return identified raw pivot levels.

        Args:
            df: DataFrame with columns [timestamp, open, high, low, close].
                 Index should be consecutive hourly bars.

        Returns:
            Dict with keys 'PH', 'PL', 'BPH', 'BPL', each containing raw PivotLevel objects.
        """
        if df.empty or len(df) < self.win_len:
            return {"PH": [], "PL": [], "BPH": [], "BPL": []}

        df = df.sort_values("timestamp").reset_index(drop=True)
        cutoff_time = df["timestamp"].iloc[-1] - pd.Timedelta(days=self.lookback_days)

        highs = df["high"].to_numpy(dtype=float)
        lows = df["low"].to_numpy(dtype=float)
        opens = df["open"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)

        effective_threshold = self.effective_intensity_threshold(highs, lows, closes)

        ph_pivots = self.detect_pivot_highs(highs)
        pl_pivots = self.detect_pivot_lows(lows)
        bph_pivots = self.detect_pivot_highs(np.maximum(opens, closes))
        bpl_pivots = self.detect_pivot_lows(np.minimum(opens, closes))

        levels = {"PH": [], "PL": [], "BPH": [], "BPL": []}

        for i in range(len(df)):
            bar_time = df["timestamp"].iloc[i]
            if bar_time < cutoff_time:
                continue

            if not np.isnan(ph_pivots[i]):
                intensity = self.calculate_intensity(i, highs, lows, is_high=True)
                if intensity >= effective_threshold:
                    levels["PH"].append(
                        PivotLevel(
                            price=float(ph_pivots[i]),
                            level_type="PH",
                            intensity=float(intensity),
                            touches=1,
                            first_seen_idx=i,
                            last_touch_idx=i,
                        )
                    )

            if not np.isnan(pl_pivots[i]):
                intensity = self.calculate_intensity(i, highs, lows, is_high=False)
                if intensity >= effective_threshold:
                    levels["PL"].append(
                        PivotLevel(
                            price=float(pl_pivots[i]),
                            level_type="PL",
                            intensity=float(intensity),
                            touches=1,
                            first_seen_idx=i,
                            last_touch_idx=i,
                        )
                    )

            if not np.isnan(bph_pivots[i]):
                body_high = float(max(opens[i], closes[i]))
                body_low = float(min(opens[i], closes[i]))
                lows_window = np.minimum(opens, closes)
                start = max(0, i - self.left_bars)
                end = min(len(df), i + self.right_bars + 1)
                intensity = (
                    body_high - np.min(lows_window[start:end])
                ) / body_high * 100 if body_high != 0 else 0.0
                if intensity >= effective_threshold:
                    levels["BPH"].append(
                        PivotLevel(
                            price=body_high,
                            level_type="BPH",
                            intensity=float(intensity),
                            touches=1,
                            first_seen_idx=i,
                            last_touch_idx=i,
                        )
                    )

            if not np.isnan(bpl_pivots[i]):
                body_low = float(min(opens[i], closes[i]))
                body_high = float(max(opens[i], closes[i]))
                highs_window = np.maximum(opens, closes)
                start = max(0, i - self.left_bars)
                end = min(len(df), i + self.right_bars + 1)
                intensity = (
                    np.max(highs_window[start:end]) - body_low
                ) / body_low * 100 if body_low != 0 else 0.0
                if intensity >= effective_threshold:
                    levels["BPL"].append(
                        PivotLevel(
                            price=body_low,
                            level_type="BPL",
                            intensity=float(intensity),
                            touches=1,
                            first_seen_idx=i,
                            last_touch_idx=i,
                        )
                    )

        return levels

    def cluster_levels(self, levels: List[PivotLevel], min_touches: Optional[int] = None) -> List[PivotZone]:
        """
        Cluster raw pivot levels into zones using the indicator's tolerance.

        Args:
            levels: Raw pivot levels sorted by type.
            min_touches: Override minimum touches for zone qualification.

        Returns:
            List of PivotZone objects.
        """
        if min_touches is None:
            min_touches = self.min_touches

        if not levels:
            return []

        sorted_levels = sorted(levels, key=lambda x: x.price)
        zones: List[PivotZone] = []
        cluster: List[PivotLevel] = [sorted_levels[0]]

        for level in sorted_levels[1:]:
            prev_price = cluster[-1].price
            if prev_price == 0 or (level.price - prev_price) / prev_price * 100 <= self.min_tol_pct:
                cluster.append(level)
            else:
                if len(cluster) >= min_touches:
                    prices = [l.price for l in cluster]
                    zones.append(
                        PivotZone(
                            level_type=cluster[0].level_type,
                            price_min=min(prices),
                            price_max=max(prices),
                            price_center=float(np.mean(prices)),
                            levels=cluster.copy(),
                        )
                    )
                cluster = [level]

        if cluster and len(cluster) >= min_touches:
            prices = [l.price for l in cluster]
            zones.append(
                PivotZone(
                    level_type=cluster[0].level_type,
                    price_min=min(prices),
                    price_max=max(prices),
                    price_center=float(np.mean(prices)),
                    levels=cluster.copy(),
                )
            )

        return zones
