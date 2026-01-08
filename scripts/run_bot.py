import argparse
import time
from src.trade_engine.engine import TradeEngine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to YAML config")
    args = parser.parse_args()

    engine = TradeEngine(args.config)
    engine.start()

    # Простейший цикл (paper), ограниченный по времени
    for _ in range(3):
        engine.poll_and_trade()
        time.sleep(1)

    # Ежедневные процедуры (пример)
    engine.reset_daily()


if __name__ == "__main__":
    main()
