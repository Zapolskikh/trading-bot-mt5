import yfinance as yf
import pandas as pd

from trading_bot_mt5.strategies.orb.calculation import RangeSizeCalculator
from trading_bot_mt5.strategies.orb.models import NYSE_SESSION, RangePeriod, Timeframe
from trading_bot_mt5.strategies.orb.strategy import ConfirmationConfig, ORBConfig, ORBStrategy

# from trading_bot_mt5.strategies.orb.utils import dataframe_to_candles
from trading_bot_mt5.strategies.orb.visualization import plot_orb_chart


# Cache for Yahoo Finance data to avoid repeated API calls
_yf_cache: dict[str, pd.DataFrame] = {}


def fetch_market_data(ticker: str = "SPY", period: str = "5d", interval: str = "5m") -> pd.DataFrame:
    """Fetch market data from Yahoo Finance with caching and timezone conversion."""
    cache_key = f"{ticker}_{period}_{interval}"
    if cache_key not in _yf_cache:
        print(f"📥 Fetching {ticker} data from Yahoo Finance ({period}, {interval})...")
        df = yf.download(ticker, period=period, interval=interval, progress=False)

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df.index.tz is not None:
            df.index = df.index.tz_convert("US/Eastern")

        # Make timezone-naive for simpler comparison
        df.index = df.index.tz_localize(None)

        _yf_cache[cache_key] = df
    return _yf_cache[cache_key].copy()


def example_visualization():
    """Demonstrating chart visualization with real data."""
    symbol = "QQQ"
    timeframe = Timeframe.M1

    df = fetch_market_data(symbol, period="1d", interval=f"{timeframe.value}m")
    df_15m = fetch_market_data(symbol, period="1d", interval="15m")  # For ATR calculation

    # Filter to get just the first trading session
    if len(df) > 0:
        first_date = df.index[0].date()
        df_day = df[df.index.date == first_date]
    else:
        print("❌ No data available")
        return

    _, max_orb_size = RangeSizeCalculator().opening_range_allowed(df_15m)

    # Configure strategy
    config = ORBConfig(
        range_period=RangePeriod.MIN_15,
        range_timeframe=timeframe,
        session=NYSE_SESSION,
        confirmation=ConfirmationConfig(
            require_close=True,
            consecutive_closes=2,
        ),
        risk_reward_target=2,
        use_range_stop_loss=True,
        stop_loss_buffer_pct=0.55,
        max_range_size=max_orb_size,
    )

    # Run strategy
    strategy = ORBStrategy(config)
    signals = strategy.process_candles(df_day)

    # Print info
    if strategy.opening_range:
        orb = strategy.opening_range
        print(f"\n📊 Opening Range ({first_date}):")
        print(f"   High: ${orb.high:.2f}")
        print(f"   Low: ${orb.low:.2f}")
        print(f"   Size: ${orb.range_size:.2f}")
        print(f"   Max Allowed: ${max_orb_size:.2f}" if max_orb_size is not None else "")

    if signals:
        signal = signals[0]
        print("\n✅ Signal Generated:")
        print(f"   Type: {signal.signal_type.value}")
        print(f"   Time: {signal.timestamp}")
        print(f"   Entry: ${signal.entry_price:.2f}")
        print(f"   Stop Loss: ${signal.stop_loss:.2f}" if signal.stop_loss else "")
        print(f"   Take Profit: ${signal.take_profit:.2f}" if signal.take_profit else "")
    else:
        signal = None
        print("\n   No breakout signals today")

    print("\n📈 Generating chart with:")
    print("   - Opening range high/low lines (green/red dashed)")
    print("   - Range midpoint (gray dotted)")
    print("   - Entry marker (triangle)")
    print("   - Stop loss line (red solid)")
    print("   - Take profit line (green solid)")
    print("   - Volume bars")

    # Plot the chart with real data
    plot_orb_chart(
        df_day,
        opening_range=strategy.opening_range,
        signal=signal,
        title=f"ORB Strategy - {symbol} {first_date} ({config.range_period.value}min Range)",
        style="yahoo",
        show_volume=False,
        show_midpoint=True,
    )


if __name__ == "__main__":
    print("🚀 ORB Strategy Examples with Real Yahoo Finance Data")
    print("=" * 60)

    example_visualization()

    print("\n" + "=" * 60)
    print("🎯 ORB Strategy Examples Complete!")
    print("=" * 60)
