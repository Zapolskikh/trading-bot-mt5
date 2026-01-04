# High-Level Design (HLD) торгового бота

Документ описывает архитектурный план торгового бота с упором на модульность, прозрачный риск-менеджмент, независимость стратегии, поддержку real-time мониторинга, телеграм-уведомления и ведение журнала в CSV.

## Кратко: что это по сути

Это архитектурный план торгового бота:
- отдельный модуль риск-менеджмента
- клиент для MetaTrader как API-обёртка
- стратегия как независимый класс
- поддержка real-time мониторинга
- алерты в Telegram
- экспорт/логика сигналов в CSV

---

## 1. Цели и требования

- Риск-менеджмент (отдельный класс):
  - Риск на сделку — фиксированный % от депозита (config)
  - Риск на день — % от депозита (config)
  - Ограничение максимального количества активных сделок
  - Динамический риск на сделку (опционально)
- MetaTrader client — один большой класс:
  1. Подключение
  2. Рыночные данные
  3. Торговые операции
  4. Позиции, ордера, история
  5. Аналитика портфеля
- Strategy class:
  1. Подготовка данных под индикаторы (таймфреймы, окно, barsize, период)
  2. Расчёт индикаторов (данные + конфиг) с добавлением значений в DataFrame объектов
  3. Entry method
  4. Exit method
  5. Real-time monitoring
  6. Расчёт пипов
- Alerts — Telegram notifications
- Журнал сделок — CSV

Нефункциональные требования:
- Надёжность: строгие проверки риска перед исполнением, идемпотентность операций.
- Наблюдаемость: логирование, метрики, алерты об ошибках.
- Тестируемость: юнит-тесты для риск-менеджмента, мок-клиент для MetaTrader.
- Производительность: минимальная задержка между сигналом и заявкой; устойчивость к сетевым сбоям.
- Безопасность: хранение секретов (Telegram токены) вне кода.

---

## 2. Общая архитектура

Компоненты:
- RiskManager — самостоятельный модуль принятия решений по риску
- MetaTraderClient — API-обёртка для взаимодействия с MetaTrader (данные и торговля)
- Strategy — независимый класс (индикаторы, вход/выход, мониторинг, пипы)
- TradeEngine (Orchestrator) — главный цикл, диспетчер событий
- AlertService — Telegram уведомления
- JournalService — запись CSV журналов (сделки, сигналы)
- PortfolioAnalytics — расчёт метрик портфеля (PnL, загрузка, VaR/опционально)

Потоки данных (высокоуровневые):
1. Market Data Ingestion: MetaTraderClient → Strategy (подготовка данных → индикаторы)
2. Signal Generation: Strategy.entry/exit → TradeEngine
3. Risk Checks: TradeEngine → RiskManager (ограничения, размеры)
4. Order Execution: TradeEngine → MetaTraderClient (place/modify/close)
5. Monitoring & Alerts: события → AlertService (Telegram)
6. Journaling: события → JournalService (CSV)
7. Feedback: исполнение ордеров → RiskManager (обновить дневной риск, активные сделки)

---

## 3. Компоненты и интерфейсы

### 3.1 RiskManager

Ответственность:
- Ограничение риска на сделку и на день
- Подсчёт объёма позиции (лот) на основе стопа и депозита
- Контроль максимального числа активных сделок
- Опциональный динамический риск (адаптация % в зависимости от контекста)

Основные входы:
- Текущий депозит/баланс/эквити
- Дистанция до стопа (в пипах/пунктах)
- Инструмент (для pip value, контрактного размера, минимального лота)
- Текущие активные сделки и дневной PnL

Основные выходы:
- Решение: can_open_trade (bool, причина)
- Расчёт размера позиции (lots)
- Обновление дневных лимитов, учёт PnL

Ключевые методы:
- init(config)
- can_open_trade(symbol, stop_distance_pips) -> (bool, reason)
- compute_position_size(symbol, stop_distance_pips, risk_pct) -> lots
- register_new_trade(trade_id, risk_amount)
- register_fill(trade_id, fill_price, lots)
- register_close(trade_id, close_price, pnl)
- remaining_daily_risk() -> currency_amount
- active_trades_count() -> int
- reset_daily_limits() (в начале торгового дня)

Инварианты:
- Суммарный риск на активные сделки ≤ дневной риск
- active_trades_count ≤ max_active_trades
- Лот ≥ min_lot и кратность шагу lot_step

Конфигурация (пример):
```yaml
risk:
  per_trade_pct: 0.5        # % от депозита на сделку
  per_day_pct: 2.0          # % от депозита на день
  max_active_trades: 4
  dynamic:
    enabled: true
    rules:
      # Пример: понижать риск при серии убытков
      drawdown_threshold_pct: 3.0
      reduce_factor: 0.5
```

Формула подсчёта размера позиции:
- risk_amount = equity * risk_pct
- stop_value = stop_distance_pips * pip_value(symbol)
- lots = risk_amount / (stop_value * contract_multiplier)
- нормировать по минимальному/шагу лота; учитывать тип инструмента (FX, CFD, Futures).

### 3.2 MetaTraderClient

Ответственность:
- Подключение к терминалу
- Чтение маркет-данных (тик/бар/таймфрейм)
- Исполнение торговых операций (рыночные/отложенные заявки)
- Управление позициями/ордерами, запрос истории
- Базовая аналитика портфеля (баланс, эквити, загрузка)

Методы (примерные):
- connect() / disconnect()
- get_market_data(symbol, timeframe, window) -> DataFrame
- get_tick(symbol) -> tick
- place_order(symbol, side, lots, sl, tp, type="market", price=None) -> order_id
- modify_order(order_id, sl=None, tp=None)
- close_position(position_id, lots=None) -> deal_id
- get_positions() -> List[Position]
- get_orders() -> List[Order]
- get_history(from, to) -> List[Deal]
- get_portfolio() -> {balance, equity, margin, free_margin}
- get_symbol_info(symbol) -> {digits, point, pip_size, contract_size, lot_step, min_lot}

Требования:
- Идемпотентность заявок: защита от повторной отправки при ретраях
- Обработка ошибок: сетевые сбои, отказ терминала, отложенные исполнения

### 3.3 Strategy

Ответственность:
- Подготовка данных под индикаторы (таймфреймы, окна, период)
- Расчёт индикаторов и запись в DataFrame
- Entry/Exit логика (сигналы)
- Real-time monitoring (состояние индикаторов/сигналов)
- Расчёт пипов для заданного инструмента

Методы:
- prepare_data(symbols, timeframes, window, barsize, period) -> dict[symbol] -> DataFrame
- compute_indicators(df, config) -> df_with_indicators
- entry(symbol, df) -> Optional[Signal]  # buy/sell, sl, tp, confidence
- exit(symbol, df, position) -> Optional[ExitSignal]  # close/partial, reason
- monitor() -> Status
- calc_pips(symbol, price_a, price_b) -> pips

Требования:
- Стратегия не должна знать о риске и торговом слое; только сигнализация.
- Конфигуратор индикаторов передаётся через config.

### 3.4 AlertService (Telegram)

Ответственность:
- Отправка уведомлений в Telegram (сигналы, исполнения, ошибки, риск-алерты)

Методы:
- send_signal(signal)
- send_order_update(order_id, status)
- send_risk_alert(message)
- send_error(error)

Конфиг:
```yaml
telegram:
  bot_token: "env:TELEGRAM_BOT_TOKEN"
  chat_id: "env:TELEGRAM_CHAT_ID"
  enabled: true
```

Типы уведомлений:
- Новый сигнал (symbol, side, price, sl/tp, confidence)
- Исполнение (order/deal id, цена, лоты)
- Риск-ограничение (отказ в открытии, превышение дневного риска)
- Ошибки (сбой подключения, отказ заявки)

### 3.5 JournalService (CSV)

Ответственность:
- Запись журналов сигналов/сделок/ошибок в CSV
- Схема столбцов, ротация файлов, консистентность

Файлы:
- trades.csv — сделки (deal-level)
- orders.csv — заявки (order-level)
- signals.csv — сигналы стратегии

Схемы (минимум):
```csv
# trades.csv
timestamp,symbol,side,entry_price,exit_price,lots,sl,tp,pnl_currency,pnl_pips,trade_id,order_id,deal_id,reason_open,reason_close,strategy_tag

# orders.csv
timestamp,symbol,side,type,price,lots,sl,tp,status,order_id,trade_id,error

# signals.csv
timestamp,symbol,side,signal_strength,price,sl,tp,comment,strategy_tag
```

---

## 4. Поток исполнения (сценарии)

### 4.1 Открытие сделки
1. Strategy.entry генерирует сигнал (side, sl, tp, confidence).
2. TradeEngine:
   - Запрашивает equity/портфель у MetaTraderClient.
   - Вычисляет stop_distance_pips.
   - Спрашивает RiskManager: can_open_trade? и compute_position_size.
   - Если ok → place_order в MetaTraderClient.
   - При успешном размещении:
     - JournalService → запись в orders.csv
     - AlertService → уведомление
     - RiskManager → register_new_trade

### 4.2 Закрытие сделки
1. Strategy.exit выдаёт сигнал закрытия или частичного закрытия.
2. TradeEngine вызывает close_position/modify_order.
3. MetaTraderClient возвращает факт сделки (deal).
4. TradeEngine:
   - JournalService → запись в trades.csv
   - RiskManager → register_close (обновить дневной риск/PnL)
   - AlertService → уведомление

### 4.3 Ежедневный цикл
- В начале дня: RiskManager.reset_daily_limits()
- Ротация CSV при необходимости
- Сброс накопительных метрик/статусов

---

## 5. Реал-тайм мониторинг

- Периодическая публикация статуса:
  - Кол-во активных сделок, дневной риск/остаток
  - Последние сигналы и индикаторы
  - Состояние подключения к MetaTrader
- Каналы:
  - CLI/лог
  - Telegram (краткие сводки)
  - Опционально: экспорт метрик (Prometheus) для дашборда

---

## 6. Расчёт пипов и размера позиции

### 6.1 Определения
- Pip: минимальный значимый шаг цены для инструмента (для FX обычно 0.0001 для большинства пар, 0.01 для JPY пар).
- Tick/point: минимальное изменение цены (в MetaTrader `point`); `digits` определяет точность.

### 6.2 Pip value и стоп
- Получить из MetaTraderClient:
  - `symbol_info.point`, `symbol_info.digits`, `symbol_info.contract_size`, `symbol_info.lot_step`, `symbol_info.min_lot`.
- Преобразование дистанции стопа:
  - stop_distance_pips = abs(entry_price - stop_price) / pip_size(symbol)
  - pip_size(symbol) зависит от инструмента: для EURUSD часто 0.0001; для USDJPY — 0.01.
- Pip value:
  - Зависит от валюты котировки и лота: pip_value ≈ contract_size * pip_size / price_conversion
  - Для точности использовать данные MetaTrader (TickValue/TickSize).

### 6.3 Размер позиции (примерная формула)
- risk_amount = equity * risk_pct
- loss_per_lot = stop_distance_pips * pip_value_per_lot
- lots = risk_amount / loss_per_lot
- Нормировать:
  - lots = round_to_step(max(min_lot, lots), lot_step)

---

## 7. Конфигурация (единый config)

Пример структуры:
```yaml
app:
  mode: "live"            # "live" | "paper" | "backtest"
  symbols: ["EURUSD","GBPUSD"]
  base_timeframe: "M15"
  data_window: 500
  barsize: "ask"          # "bid" | "ask" | "mid"

risk:
  per_trade_pct: 0.5
  per_day_pct: 2.0
  max_active_trades: 4
  dynamic:
    enabled: false

strategy:
  name: "MyStrategyV1"
  indicators:
    - type: "EMA"
      period: 20
    - type: "EMA"
      period: 50
    - type: "ATR"
      period: 14
  entry:
    min_signal_strength: 0.6
  exit:
    atr_multiplier_sl: 1.5
    atr_multiplier_tp: 2.0

metatrader:
  terminal_path: "/path/to/terminal"
  account_id: 123456
  server: "Broker-Server"
  timeout_ms: 2000
  retry:
    attempts: 3
    backoff_ms: 500

telegram:
  enabled: true
  bot_token: "env:TELEGRAM_BOT_TOKEN"
  chat_id: "env:TELEGRAM_CHAT_ID"

journal:
  path: "./journal"
  rotate_daily: true
```

---

## 8. TradeEngine (Оркестратор)

Ответственность:
- Главный цикл событий (poll данных, запуск стратегии, риск-проверки, исполнение)
- Планировщик таймфреймов
- Обработка состояний ордеров/позиций
- Ведение кэшей (последние бары/индикаторы)
- Границы и ретраи

Состояния заявки (state machine):
- NEW → PLACED → FILLED → PARTIALLY_FILLED → CLOSED
- Ошибки: REJECTED, EXPIRED, CANCELLED
- Переходы фиксируются в orders.csv; исполнения — в trades.csv.

---

## 9. Ошибки и отказоустойчивость

- Ретраи на сетевые ошибки (экспоненциальный backoff)
- Идемпотентность: ключи клиента/ид заявок, защита от дублей
- Фэйл-сейф:
  - При потере соединения — пауза сигналов, уведомление, попытка реконнекта
  - При превышении дневного риска — жёсткая блокировка новых сделок
- Валидация параметров инструмента (min_lot, lot_step)

---

## 10. Безопасность

- Секреты (Telegram токены) — только из окружения/секрет-хранилища
- Разделение прав доступа к терминалу/аккаунту
- Логи без чувствительных данных

---

## 11. Тестирование и качество

- Юнит-тесты:
  - RiskManager: вычисление лотов, лимиты, дневной риск, динамика риска
  - Strategy: корректность индикаторов/сигналов на синтетических данных
- Интеграционные тесты:
  - Мок MetaTraderClient для ордеров/позиций
- Backtest режим (опционально):
  - Чтение исторических данных, симуляция исполнений
- Верификация CSV схем (колонки, типы, ротация)

---

## 12. Метрики и наблюдаемость

- Метрики:
  - latency_signal_to_order_ms
  - orders_placed, deals_filled, rejects
  - active_trades_count
  - daily_risk_used_pct
- Логи:
  - уровень INFO/ERROR, трассировка исключений
- Алерты:
  - Ошибки подключения, превышение риска, отказ заявок

---

## 13. Развёртывание и окружение

- Окружение:
  - Python + MetaTrader терминал (MT5 предпочтительно)
  - Зависимости: pandas, numpy, requests/aiogram (для Telegram), логирование
- Конфиг через YAML + env-переменные
- Запуск:
  - systemd/PM2/докер (по необходимости)
- Права и путь к терминалу MetaTrader

---

## 14. Дорожная карта (MVP → расширения)

- MVP:
  - MetaTraderClient (подключение, данные, базовые торговые операции)
  - Strategy с 1–2 индикаторами, Entry/Exit
  - RiskManager с фиксированным риском на сделку/день + лимит активных сделок
  - JournalService (CSV) и AlertService (Telegram)
  - TradeEngine (один таймфрейм, базовый цикл)
- Расширения:
  - Динамический риск-менеджмент
  - Мульти-таймфреймы, несколько стратегий
  - Частичное закрытие, траллинг-стоп
  - Метрики/дашборд
  - Backtest/реплей
  - Портфельная аналитика (VaR, экспозиции)

---

## 15. Риски и допущения

- Зависимость от стабильности терминала MetaTrader и брокерского API
- Точность pip value и параметров инструмента может отличаться между брокерами — обязательна валидация
- Сетевые/локальные сбои — необходимы надёжные ретраи и алерты
- Стратегия должна оставаться чистой от торговых/рисковых деталей (принцип разделения ответственности)

---