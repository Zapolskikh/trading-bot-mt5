import pandas as pd
from src.strategy.strategy import Strategy


def test_compute_indicators_noop():
    st = Strategy(config={"indicators": []})
    df = pd.DataFrame({"close": [1, 2, 3]})
    out = st.compute_indicators(df, st.config)
    assert list(out.columns) == ["close"]