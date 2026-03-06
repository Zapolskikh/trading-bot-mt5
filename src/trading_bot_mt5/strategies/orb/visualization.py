import pandas as pd
import mplfinance as mpf

from trading_bot_mt5.strategies.orb.utils import candles_to_dataframe
from trading_bot_mt5.strategies.orb.models import Candle, OpeningRange, Signal, SignalType


def create_range_lines(
    opening_range: OpeningRange,
    show_midpoint: bool = True,
) -> list[dict]:
    """
    Create horizontal lines for the opening range levels.
    """
    hlines = []

    # Range high line (resistance)
    hlines.append(
        {
            "hlines": opening_range.high,
            "colors": "green",
            "linestyle": "--",
            "linewidths": 1.5,
        }
    )

    # Range low line (support)
    hlines.append(
        {
            "hlines": opening_range.low,
            "colors": "red",
            "linestyle": "--",
            "linewidths": 1.5,
        }
    )

    # Midpoint line (optional)
    if show_midpoint:
        hlines.append(
            {
                "hlines": opening_range.midpoint,
                "colors": "gray",
                "linestyle": ":",
                "linewidths": 1.0,
            }
        )

    return hlines


def create_signal_markers(
    signal: Signal,
    df: pd.DataFrame,
) -> tuple[list, list]:
    """
    Create marker data for entry, stop loss, and take profit levels.
    """
    addplots: list = []
    hlines: list = []

    # Find the signal candle index
    signal_time = signal.timestamp
    if signal_time not in df.index:
        return addplots, hlines

    # Create entry marker
    marker_data = pd.Series(index=df.index, dtype=float)
    marker_data[:] = float("nan")
    marker_data[signal_time] = signal.entry_price

    if signal.signal_type == SignalType.LONG:
        marker = "^"
        color = "lime"
    else:
        marker = "v"
        color = "red"

    addplots.append(
        mpf.make_addplot(
            marker_data,
            type="scatter",
            markersize=150,
            marker=marker,
            color=color,
        )
    )

    # Stop loss line
    if signal.stop_loss is not None:
        hlines.append(
            {
                "hlines": signal.stop_loss,
                "colors": "red",
                "linestyle": "-",
                "linewidths": 2.0,
            }
        )

    # Take profit line
    if signal.take_profit is not None:
        hlines.append(
            {
                "hlines": signal.take_profit,
                "colors": "green",
                "linestyle": "-",
                "linewidths": 2.0,
            }
        )

    return addplots, hlines


def plot_orb_chart(
    candles: list[Candle] | pd.DataFrame,
    opening_range: OpeningRange | None = None,
    signal: Signal | None = None,
    title: str = "Opening Range Breakout",
    style: str = "yahoo",
    show_volume: bool = True,
    show_midpoint: bool = True,
    save_path: str | None = None,
    show: bool = True,
) -> None:
    """
    Plot a candlestick chart with opening range levels and signals.
    """
    # Handle both DataFrame and Candle list inputs
    if isinstance(candles, pd.DataFrame):
        df = candles.copy()
        # Normalize column names
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
        if not isinstance(df.columns[0], str) or df.columns[0].lower() not in [
            "open",
            "high",
            "low",
            "close",
        ]:
            # Columns might need title case for mplfinance
            df.columns = [str(c).title() for c in df.columns]
    else:
        df = candles_to_dataframe(candles)

    # Build plot configuration
    addplots = []
    all_hlines = []

    # Add opening range lines
    if opening_range is not None:
        range_hlines = create_range_lines(opening_range, show_midpoint)
        all_hlines.extend(range_hlines)

    # Add signal markers and levels
    if signal is not None:
        signal_addplots, signal_hlines = create_signal_markers(signal, df)
        addplots.extend(signal_addplots)
        all_hlines.extend(signal_hlines)

    # Combine all hlines
    combined_hlines = None
    if all_hlines:
        combined_hlines = {
            "hlines": [h["hlines"] for h in all_hlines],
            "colors": [h["colors"] for h in all_hlines],
            "linestyle": [h["linestyle"] for h in all_hlines],
            "linewidths": [h["linewidths"] for h in all_hlines],
        }

    # Plot configuration
    kwargs = {
        "type": "candle",
        "style": style,
        "title": title,
        "volume": show_volume,
        "warn_too_much_data": 1000,
        "scale_padding": {"left": 0.5, "top": 0.5, "right": 0.7, "bottom": 0.5},
    }

    if combined_hlines:
        kwargs["hlines"] = combined_hlines

    if addplots:
        kwargs["addplot"] = addplots

    if save_path:
        kwargs["savefig"] = save_path

    if show:
        mpf.plot(df, **kwargs)
    else:
        kwargs["returnfig"] = True
        return mpf.plot(df, **kwargs)
