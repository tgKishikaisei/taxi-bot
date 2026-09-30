# Taxi Bot

Бот такси в Telegram на pyTelegramBotAPI и PostgreSQL. Пассажир отправляет точку подачи и назначения геолокацией или адресом и называет цену. Таксист выходит на линию, видит заказы в радиусе 15 км и берёт один; второй водитель тот же заказ уже не получит.

[![License](https://img.shields.io/github/license/tgKishikaisei/taxi-bot)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/tgKishikaisei/taxi-bot/ci.yml?branch=main&label=CI)](https://github.com/tgKishikaisei/taxi-bot/actions/workflows/ci.yml)

## Что умеет

- **Пассажир.** Регистрация по своему контакту, заказ с точками на карте или адресом текстом, цена целым числом, отмена активного заказа с уведомлением водителя, история поездок.
- **Таксист.** Регистрация с маркой, номером и фото машины, выход на линию, поиск ближайших заказов, счётчик водителей онлайн.
- **Карты.** Геокодер Яндекса переводит адрес в координаты и обратно, статичная карта показывает точку подачи, ссылки ведут в Google Maps.
- **Интерфейс** на русском и узбекском, язык меняется только у того, кто его выбрал.

Заказ принимается одним атомарным `UPDATE ... WHERE`, поэтому два водителя не возьмут его одновременно.

## Стек

Python 3.12, pyTelegramBotAPI, PostgreSQL (psycopg2), Yandex Geocoder и Static Maps, Pillow.

## Запуск

```bash
git clone https://github.com/tgKishikaisei/taxi-bot.git
cd taxi-bot
python -m venv venv
venv\Scripts\activate               # Linux и macOS: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # TELEGRAM_BOT_TOKEN_2, YANDEX_GEOCODER_API_KEY, DB_*
python app.py
```

Таблицы создаются и обновляются при старте. Ключ геокодера выдаёт кабинет разработчика Яндекса: https://developer.tech.yandex.ru/.

## Тесты

```bash
pip install pytest
python -m pytest -q
```

Тесты работы с базой запускаются, если задать `TAXI_TEST_DB=postgresql://...` с пустой базой: они удаляют и создают таблицы заново.

## Демо

Скриншотов нет: бот работает в Telegram, запустите его со своим токеном от @BotFather.

## Лицензия

[MIT](LICENSE) © 2026 Behruz Avezmatov
