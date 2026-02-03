# TODO - Trading Bot MT5

## MVP Готов ✅

### Следующие шаги

#### 1. Создать реальную торговую стратегию
- [ ] Разработать EMA Crossover стратегию в `strategies/ema_crossover.py`
- [ ] Или Support/Resistance стратегию в `strategies/levels.py`
- [ ] Протестировать на исторических данных

#### 2. Тестирование на Demo счете
- [ ] Настроить .env с demo credentials
- [ ] Запустить бота с новой стратегией
- [ ] Мониторить результаты 1-2 недели

#### 3. Position Manager
- [ ] Trailing Stop функционал
- [ ] Break-even перемещение SL
- [ ] Частичное закрытие позиций

#### 4. State Persistence
- [ ] Сохранение состояния в JSON при остановке
- [ ] Восстановление при запуске
- [ ] Сохранение активных позиций и настроек стратегии

#### 5. Production Hardening
- [ ] Error handling и retry логика
- [ ] Автоматическое переподключение к MT5
- [ ] Graceful shutdown
- [ ] Логирование в файлы + rotation

#### 6. Backtest Mode
- [ ] Загрузка исторических данных
- [ ] Симуляция торговли
- [ ] Отчеты о результатах

#### 7. Advanced Features (Later)
- [ ] Web UI Dashboard
- [ ] Database вместо CSV
- [ ] Multi-account support
- [ ] Performance metrics (Sharpe, Max DD, Win Rate)
- [ ] Telegram bot commands (status, stop, start)

---

## Архитектура (Текущая)

```
main.py              -> TradingBot (универсальный экзекьютор)
run.py               -> CLI entry point
strategies/          -> Торговая логика
src/
  ├── metatrader_client/  -> MT5 API
  ├── risk_manager/       -> Position sizing & limits
  ├── alert_service/      -> Telegram
  ├── journal_service/    -> CSV logging
  ├── strategy/           -> Base Strategy class
  └── common/             -> Config, types
```

## Запуск

```bash
# Установка
poetry install

# Настройка .env
cp .env.example .env
# Отредактировать .env с credentials

# Запуск
python run.py --config config/config.yaml --strategy simple_test --cycles 3
```

## Статус компонентов

- ✅ MetaTraderClient - готов
- ✅ RiskManager - готов
- ✅ AlertService - готов
- ✅ JournalService - готов
- ✅ Base Strategy - готов
- ✅ TradingBot (main.py) - готов
- ⚠️ Real Strategy - нужна разработка
- ⚠️ Position Manager - TODO
- ⚠️ State Persistence - TODO
