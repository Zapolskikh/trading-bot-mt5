from src.trade_engine.engine import TradeEngine
import os


def test_engine_init(tmp_path):
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        """
app:
  mode: "paper"
  symbols: ["EURUSD"]
  base_timeframe: "M1"
  data_window: 100
  barsize: "ask"
risk:
  per_trade_pct: 1.0
  per_day_pct: 2.0
  max_active_trades: 2
strategy: {}
metatrader: {}
telegram:
  enabled: false
journal:
  path: "%s"
  rotate_daily: false
""" % (tmp_path / "journal"),
        encoding="utf-8",
    )

    engine = TradeEngine(str(cfg_path))
    assert engine.mt is not None
    assert engine.risk is not None
    assert engine.strategy is not None
    assert os.path.isdir(tmp_path / "journal")
