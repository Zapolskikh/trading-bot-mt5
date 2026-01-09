# Торговый бот — скелет проекта [![Code check, unit test and fix dependencies](https://github.com/Zapolskikh/trading-bot-mt5/actions/workflows/ci-code-check.yaml/badge.svg?branch=main)](https://github.com/Zapolskikh/trading-bot-mt5/actions/workflows/ci-code-check.yaml)

Скелет проекта на основе HLD-архитектуры: модульный риск-менеджмент, клиент MetaTrader, независимая стратегия, TradeEngine-оркестратор, real-time мониторинг, Telegram-алерты и CSV-журнал.

## Настройки для старта разработки
- установить `Choco` на свой Windows [инструкция](https://chocolatey.org/install#individual)
- установить `make` на свой компьютер
```shell
choco install make
```
- установить библиотеки и все зависимости, используй `make`
```shell
make install
```
- заполни `.env` из `.env.example`
- настрой config: `config/config.yaml` (копия из `config/config.example.yaml`)
- запустить unit tests локально
```shell
make test
```
- запустить проверку кода (статический и динамический анализ, линковщик, тд)
```shell
make check
```
- запусти: `python scripts/run_bot.py --config config/config.yaml`

## Структура
Смотри [ProjectStructure](docs/ProjectStructure.md).

## Цели, модули и задачи
Смотри [Workplan](docs/Workplan.md).

## Примечание
Проект — каркас; реализация методов помечена TODO по HLD.
