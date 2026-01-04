# Структура проекта (скелет)

```
.
├── README.md
├── requirements.txt
├── .env.example
├── config
│   ├── config.yaml                # основной конфиг (создать из example)
│   └── config.example.yaml        # пример конфига
├── docs
│   ├── HLD.md                     # high-level design (исходная документация)
│   ├── ProjectStructure.md        # текущий файл
│   └── Workplan.md                # цели/модули/задачи
├── scripts
│   └── run_bot.py                 # точка входа (оркестратор)
├── src
│   ├── common
│   │   ├── config.py              # загрузчик конфига
│   │   └── types.py               # типы данных: Signal, ExitSignal, Order, Position
│   ├── risk_manager
│   │   └── risk_manager.py        # класс RiskManager
│   ├── metatrader_client
│   │   └── client.py              # класс MetaTraderClient
│   ├── strategy
│   │   └── strategy.py            # базовая Strategy
│   ├── trade_engine
│   │   └── engine.py              # TradeEngine (оркестратор)
│   ├── alert_service
│   │   └── telegram.py            # Telegram-уведомления
│   └── journal_service
│       └── csv_journal.py         # CSV-журнал
└── tests
    ├── conftest.py
    ├── test_risk_manager.py
    ├── test_strategy.py
    └── test_engine_integration.py
```