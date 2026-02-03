# Strategies folder

Place your trading strategies here.

## Structure

Each strategy should:
1. Inherit from `src.strategy.strategy.Strategy`
2. Implement `entry()` method (required)
3. Optionally implement `exit()`, `compute_indicators()`, `monitor()`

## Example

```python
# strategies/my_strategy.py

from src.strategy.strategy import Strategy
from src.common.types import Signal
import pandas as pd


class MyStrategy(Strategy):
    def entry(self, symbol, df):
        # Your entry logic
        return Signal(...)
```

## Usage

```bash
python run.py --config config/config.yaml --strategy my_strategy
```

The bot will automatically load `strategies/my_strategy.py`.
