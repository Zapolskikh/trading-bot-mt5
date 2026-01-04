# Торговый бот — скелет проекта

Скелет проекта на основе HLD-архитектуры: модульный риск-менеджмент, клиент MetaTrader, независимая стратегия, TradeEngine-оркестратор, real-time мониторинг, Telegram-алерты и CSV-журнал.

## Структура
Смотри [ProjectStructure](docs/ProjectStructure.md).

## Цели, модули и задачи
Смотри [Workplan](docs/Workplan.md).

## Быстрый старт (скелет)
- Настрой config: `config/config.yaml` (копия из `config/config.example.yaml`)
- Установи зависимости: `pip install -r requirements.txt`
- Заполни `.env` из `.env.example`
- Запусти: `python scripts/run_bot.py --config config/config.yaml`

## Примечание
Проект — каркас; реализация методов помечена TODO по HLD.