import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import mplfinance as mpf
import io

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

    hlines.append(
        {
            "hlines": opening_range.high,
            "colors": "green",
            "linestyle": "--",
            "linewidths": 1.5,
        }
    )

    hlines.append(
        {
            "hlines": opening_range.low,
            "colors": "red",
            "linestyle": "--",
            "linewidths": 1.5,
        }
    )

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

    signal_time = signal.timestamp
    if signal_time not in df.index:
        return addplots, hlines

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

    if signal.stop_loss is not None:
        hlines.append(
            {
                "hlines": signal.stop_loss,
                "colors": "red",
                "linestyle": "-",
                "linewidths": 2.0,
            }
        )

    if signal.take_profit is not None:
        hlines.append(
            {
                "hlines": signal.take_profit,
                "colors": "green",
                "linestyle": "-",
                "linewidths": 2.0,
            }
        )

    if signal.vwap is not None:
        hlines.append(
            {
                "hlines": signal.vwap,
                "colors": "blue",
                "linestyle": "-.",
                "linewidths": 1.5,
            }
        )

    return addplots, hlines


def _normalize_dataframe(candles: list[Candle] | pd.DataFrame) -> pd.DataFrame:
    """Normalize input to a properly-columned DataFrame for mplfinance."""
    if isinstance(candles, pd.DataFrame):
        df = candles.copy()
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
        if not isinstance(df.columns[0], str) or df.columns[0].lower() not in (
            "open",
            "high",
            "low",
            "close",
        ):
            df.columns = [str(c).title() for c in df.columns]
    else:
        df = candles_to_dataframe(candles)
    return df


def _build_legend(
    ax: plt.Axes,
    opening_range: OpeningRange | None,
    signal: Signal | None,
    show_midpoint: bool,
) -> None:
    """
    Add a legend to the price axis describing all plotted levels and signals.
    """
    handles = []

    if opening_range is not None:
        handles.append(
            mlines.Line2D(
                [],
                [],
                color="green",
                linestyle="--",
                linewidth=1.5,
                label=f"Range High ({opening_range.high:.5g})",
            )
        )
        handles.append(
            mlines.Line2D(
                [],
                [],
                color="red",
                linestyle="--",
                linewidth=1.5,
                label=f"Range Low ({opening_range.low:.5g})",
            )
        )
        if show_midpoint:
            handles.append(
                mlines.Line2D(
                    [],
                    [],
                    color="gray",
                    linestyle=":",
                    linewidth=1.0,
                    label=f"Midpoint ({opening_range.midpoint:.5g})",
                )
            )

    if signal is not None:
        if signal.signal_type == SignalType.LONG:
            handles.append(
                mlines.Line2D(
                    [],
                    [],
                    marker="^",
                    color="lime",
                    linestyle="None",
                    markersize=10,
                    label=f"Long Entry ({signal.entry_price:.5g})",
                )
            )
        else:
            handles.append(
                mlines.Line2D(
                    [],
                    [],
                    marker="v",
                    color="red",
                    linestyle="None",
                    markersize=10,
                    label=f"Short Entry ({signal.entry_price:.5g})",
                )
            )

        if signal.stop_loss is not None:
            handles.append(
                mlines.Line2D(
                    [],
                    [],
                    color="red",
                    linestyle="-",
                    linewidth=2.0,
                    label=f"Stop Loss ({signal.stop_loss:.5g})",
                )
            )
        if signal.take_profit is not None:
            handles.append(
                mlines.Line2D(
                    [],
                    [],
                    color="green",
                    linestyle="-",
                    linewidth=2.0,
                    label=f"Take Profit ({signal.take_profit:.5g})",
                )
            )

        if signal.vwap is not None:
            handles.append(
                mlines.Line2D(
                    [],
                    [],
                    color="blue",
                    linestyle="-.",
                    linewidth=1.5,
                    label=f"VWAP ({signal.vwap:.5g})",
                )
            )

    if handles:
        ax.legend(
            handles=handles,
            loc="upper left",
            fontsize=8,
            framealpha=0.8,
            fancybox=True,
        )


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
    return_bytes: bool = False,
) -> tuple[plt.Figure, list[plt.Axes]] | bytes | None:
    """
    Plot a candlestick chart with opening range levels, signals, and a legend.

    Returns (fig, axes) when show=False and return_bytes=False, bytes when return_bytes=True, otherwise None.
    """
    df = _normalize_dataframe(candles)

    addplots: list = []
    all_hlines: list = []

    if opening_range is not None:
        all_hlines.extend(create_range_lines(opening_range, show_midpoint))

    if signal is not None:
        signal_addplots, signal_hlines = create_signal_markers(signal, df)
        addplots.extend(signal_addplots)
        all_hlines.extend(signal_hlines)

    combined_hlines = None
    if all_hlines:
        combined_hlines = {
            "hlines": [h["hlines"] for h in all_hlines],
            "colors": [h["colors"] for h in all_hlines],
            "linestyle": [h["linestyle"] for h in all_hlines],
            "linewidths": [h["linewidths"] for h in all_hlines],
        }

    kwargs: dict = {
        "type": "candle",
        "style": style,
        "title": title,
        "volume": show_volume,
        "warn_too_much_data": 1000,
        "scale_padding": {"left": 0.5, "top": 0.5, "right": 0.7, "bottom": 0.5},
        "returnfig": True,  # always capture so we can add the legend
    }

    if combined_hlines:
        kwargs["hlines"] = combined_hlines
    if addplots:
        kwargs["addplot"] = addplots

    fig, axes = mpf.plot(df, **kwargs)

    # axes[0] is the price panel; axes[1] is volume (if shown)
    _build_legend(axes[0], opening_range, signal, show_midpoint)

    if save_path:
        fig.savefig(save_path, bbox_inches="tight")

    if show:
        plt.show()
        return None

    if return_bytes:
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", bbox_inches="tight")
        buffer.seek(0)
        chart_bytes = buffer.getvalue()
        plt.close(fig)  # Clean up the figure
        return chart_bytes

    return fig, axes
