#!/usr/bin/env python3
"""
Runner script для запуска торгового бота.

Использование:
    python run.py --config config/config.yaml --strategy simple_test
    python run.py --config config/config.yaml --strategy simple_test --cycles 10
"""

import argparse
from main import main


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="MT5 Trading Bot Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Запуск с тестовой стратегией (бесконечно)
  python run.py --config config/config.yaml --strategy simple_test

  # Запуск с ограничением циклов
  python run.py --config config/config.yaml --strategy my_strategy --cycles 10

  # Стратегии берутся из папки strategies/
  # Например: strategies/simple_test.py
        """,
    )

    parser.add_argument("--config", required=True, help="Путь к YAML конфигу (например: config/config.yaml)")

    parser.add_argument("--strategy", required=True, help="Имя стратегии из папки strategies/ (без .py)")

    parser.add_argument(
        "--cycles", type=int, default=None, help="Количество торговых циклов (по умолчанию: бесконечно)"
    )

    args = parser.parse_args()

    # Запуск бота
    main(config_path=args.config, strategy_name=args.strategy, cycles=args.cycles)
