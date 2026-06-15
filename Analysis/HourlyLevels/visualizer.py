"""
Matplotlib visualization for hourly inflection levels.
Plots price, pivots, levels with touch counts, and zone clusters.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.dates import DateFormatter, AutoDateLocator
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from .inflection_levels import PivotLevel, PivotZone


class LevelsVisualizer:
    """Plots inflection levels, zones, and price action."""

    COLOR_MAP = {
        "PH": {"main": "#FF6B6B", "zone": "#FFE5E5"},  # Red (resistance)
        "PL": {"main": "#4ECDC4", "zone": "#E5F9F7"},  # Teal (support)
        "BPH": {"main": "#FFB84D", "zone": "#FFE6CC"},  # Orange (body resistance)
        "BPL": {"main": "#95E1D3", "zone": "#E5F9F5"},  # Light teal (body support)
    }

    LABEL_MAP = {
        "PH": "Pivot High (Wick)",
        "PL": "Pivot Low (Wick)",
        "BPH": "Body Pivot High",
        "BPL": "Body Pivot Low",
    }

    def __init__(self, figsize: tuple = (16, 8)):
        self.figsize = figsize

    def plot(
        self,
        df: pd.DataFrame,
        levels_by_type: Dict[str, List[PivotLevel]],
        zones_by_type: Dict[str, List[PivotZone]],
        title: str = "Hourly Inflection Levels",
        show_volume: bool = False,
        show_zones: bool = True,
        show_labels: bool = True,
    ) -> plt.Figure:
        """
        Plot price and inflection levels.

        Args:
            df: DataFrame with [timestamp, open, high, low, close, volume] (hourly OHLC).
            levels_by_type: Dict with keys 'PH', 'PL', 'BPH', 'BPL' containing level lists.
            zones_by_type: Dict with keys 'PH', 'PL', 'BPH', 'BPL' containing zone lists.
            title: Chart title.
            show_volume: If True, add volume subplot below price.
            show_zones: If True, shade zone regions.
            show_labels: If True, show touch counts and intensity on labels.

        Returns:
            matplotlib Figure object.
        """
        n_rows = 2 if show_volume else 1
        fig, axes = plt.subplots(n_rows, 1, figsize=self.figsize, sharex=True)
        if not show_volume:
            axes = [axes]

        ax_price = axes[0]

        # Plot candlesticks
        df_plot = df.copy()
        df_plot.index = pd.to_datetime(df_plot["timestamp"])

        # Collect all prices that are part of zones
        zoned_prices = set()
        if show_zones:
            for level_type in ["PH", "PL", "BPH", "BPL"]:
                zones = zones_by_type.get(level_type, [])
                for zone in zones:
                    # Add all level prices in this zone to the set
                    for level in zone.levels:
                        zoned_prices.add(round(level.price, 2))

        # Draw zones FIRST with light yellow color (so they appear behind candlesticks)
        if show_zones:
            for level_type in ["PH", "PL", "BPH", "BPL"]:
                zones = zones_by_type.get(level_type, [])
                for zone in zones:
                    # Draw shaded zone with light yellow
                    ax_price.axhspan(
                        zone.price_min,
                        zone.price_max,
                        alpha=0.35,
                        color="#FFFF99",  # Light yellow
                        zorder=0,
                        linewidth=0,
                    )
                    # Add YELLOW border lines at top and bottom of zone
                    ax_price.axhline(
                        zone.price_max,
                        color="#FFD700",  # Gold/Yellow
                        linestyle="-",
                        linewidth=2.0,
                        alpha=0.8,
                        zorder=1,
                    )
                    ax_price.axhline(
                        zone.price_min,
                        color="#FFD700",  # Gold/Yellow
                        linestyle="-",
                        linewidth=2.0,
                        alpha=0.8,
                        zorder=1,
                    )

        # Draw candlesticks
        colors = ["g" if c >= o else "r" for o, c in zip(df_plot["open"], df_plot["close"])]
        widths = 0.6
        for i, (idx, row) in enumerate(df_plot.iterrows()):
            body_height = abs(row["close"] - row["open"])
            body_bottom = min(row["close"], row["open"])
            wick_color = colors[i]

            # Wick
            ax_price.plot([i, i], [row["low"], row["high"]], color=wick_color, linewidth=0.5, alpha=0.7, zorder=2)

            # Body
            rect = mpatches.Rectangle(
                (i - widths / 2, body_bottom),
                widths,
                body_height,
                facecolor=colors[i],
                edgecolor=wick_color,
                linewidth=1,
                alpha=0.8,
                zorder=2,
            )
            ax_price.add_patch(rect)

        # Draw level lines with labels
        for level_type in ["PH", "PL", "BPH", "BPL"]:
            levels = levels_by_type.get(level_type, [])
            level_color = self.COLOR_MAP[level_type]["main"]
            linestyle = "-" if level_type in ["PH", "BPH"] else "--"

            for level in levels:
                # Check if this level is part of a zone
                price_rounded = round(level.price, 2)
                is_zoned = price_rounded in zoned_prices
                
                # Use gray for unzoned levels, original color for zoned levels
                line_color = level_color if is_zoned else "#888888"  # Gray for unzoned
                line_alpha = 0.7 if is_zoned else 0.4
                
                ax_price.axhline(
                    level.price, color=line_color, linestyle=linestyle, linewidth=1.5, alpha=line_alpha, zorder=3
                )

                if show_labels:
                    label_text = f"{level.price:.2f} ({level.touches}x, {level.intensity:.1f}%)"
                    label_color = level_color if is_zoned else "#888888"
                    ax_price.text(
                        len(df_plot) - 1,
                        level.price,
                        label_text,
                        fontsize=8,
                        color=label_color,
                        va="center",
                        ha="right",
                        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.7),
                    )

        # Set price axis limits
        all_prices = np.concatenate([df_plot["high"].values, df_plot["low"].values])
        price_range = all_prices.max() - all_prices.min()
        ax_price.set_ylim(all_prices.min() - 0.05 * price_range, all_prices.max() + 0.05 * price_range)

        ax_price.set_title(title, fontsize=14, fontweight="bold")
        ax_price.set_ylabel("Price", fontsize=11)
        ax_price.grid(True, alpha=0.3)

        # Volume subplot
        if show_volume and len(axes) > 1:
            ax_vol = axes[1]
            colors_vol = ["g" if c >= o else "r" for o, c in zip(df_plot["open"], df_plot["close"])]
            ax_vol.bar(range(len(df_plot)), df_plot["volume"], color=colors_vol, alpha=0.6, width=0.6)
            ax_vol.set_ylabel("Volume", fontsize=11)
            ax_vol.grid(True, alpha=0.3)

        # X-axis formatting
        ax_price.set_xticks(range(0, len(df_plot), max(1, len(df_plot) // 10)))
        ax_price.set_xticklabels(
            [df_plot.index[i].strftime("%m-%d %H:%M") if i < len(df_plot) else "" 
             for i in range(0, len(df_plot), max(1, len(df_plot) // 10))],
            rotation=45,
            ha="right",
        )

        # Legend
        legend_elements = []
        for level_type in ["PH", "PL", "BPH", "BPL"]:
            if level_type in levels_by_type and levels_by_type[level_type]:
                linestyle = "-" if level_type in ["PH", "BPH"] else "--"
                legend_elements.append(
                    mpatches.Patch(color=self.COLOR_MAP[level_type]["main"], label=self.LABEL_MAP[level_type])
                )
        if legend_elements:
            ax_price.legend(handles=legend_elements, loc="upper left", fontsize=10)

        plt.tight_layout()
        return fig

    def save(self, fig: plt.Figure, filepath: str) -> None:
        """Save figure to file."""
        fig.savefig(filepath, dpi=150, bbox_inches="tight")
        print(f"Chart saved to {filepath}")

    def show(self, fig: plt.Figure) -> None:
        """Display figure."""
        plt.show()
