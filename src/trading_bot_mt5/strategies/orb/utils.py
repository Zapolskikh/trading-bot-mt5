import pandas as pd

from trading_bot_mt5.strategies.orb.models import Candle


def dataframe_to_candles(df: pd.DataFrame) -> list[Candle]:
    """Convert a pandas DataFrame to a list of Candle objects."""
    # Normalize column names to lowercase
    df_normalized = df.copy()
    df_normalized.columns = df_normalized.columns.str.lower()

    # Handle multi-level columns from yfinance (e.g., ('Open', 'AAPL'))
    if isinstance(df_normalized.columns, pd.MultiIndex):
        df_normalized.columns = df_normalized.columns.get_level_values(0).str.lower()

    # Ensure we have required columns
    required = {"open", "high", "low", "close"}
    available = set(df_normalized.columns)
    missing = required - available

    if missing:
        raise ValueError(f"DataFrame missing required columns: {missing}")

    # Convert index to datetime if needed
    if not isinstance(df_normalized.index, pd.DatetimeIndex):
        if "date" in df_normalized.columns:
            df_normalized.index = pd.to_datetime(df_normalized["date"])
        elif "datetime" in df_normalized.columns:
            df_normalized.index = pd.to_datetime(df_normalized["datetime"])
        elif "timestamp" in df_normalized.columns:
            df_normalized.index = pd.to_datetime(df_normalized["timestamp"])
        else:
            raise ValueError("DataFrame must have DatetimeIndex or a date/datetime/timestamp column")

    candles = []
    for timestamp, row in df_normalized.iterrows():
        candle = Candle(
            timestamp=timestamp.to_pydatetime(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0)),
        )
        candles.append(candle)

    return candles


def candles_to_dataframe(candles: list[Candle]) -> pd.DataFrame:
    """Convert a list of Candle objects to a pandas DataFrame."""
    data = {
        "Open": [c.open for c in candles],
        "High": [c.high for c in candles],
        "Low": [c.low for c in candles],
        "Close": [c.close for c in candles],
        "Volume": [c.volume for c in candles],
    }
    index = pd.DatetimeIndex([c.timestamp for c in candles])
    df = pd.DataFrame(data, index=index)
    df.index.name = "Date"
    return df


def normalize_candle_data(data: list[Candle] | pd.DataFrame) -> list[Candle]:
    """Normalize input data to a list of Candle objects."""
    if isinstance(data, pd.DataFrame):
        return dataframe_to_candles(data)
    return data


def validate_dataframe(df: pd.DataFrame) -> tuple[bool, list[str]]:
    """Validate that a DataFrame has the required structure for ORB strategy."""
    issues = []

    # Check columns
    df_lower = df.columns.str.lower()
    required = {"open", "high", "low", "close"}

    # Handle multi-index columns
    if isinstance(df.columns, pd.MultiIndex):
        df_lower = df.columns.get_level_values(0).str.lower()

    available = set(df_lower)
    missing = required - available
    if missing:
        issues.append(f"Missing columns: {missing}")

    if not isinstance(df.index, pd.DatetimeIndex):
        has_date_col = any(col in df_lower for col in ["date", "datetime", "timestamp"])
        if not has_date_col:
            issues.append("No DatetimeIndex or date column found")

    if len(df) == 0:
        issues.append("DataFrame is empty")

    if df.isnull().any().any():
        nan_cols = df.columns[df.isnull().any()].tolist()
        issues.append(f"NaN values found in columns: {nan_cols}")

    return len(issues) == 0, issues
