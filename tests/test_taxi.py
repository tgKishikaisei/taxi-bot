"""Тесты Taxibot на настоящем PostgreSQL, без сети Telegram и Яндекса.

Нужна пустая тестовая база, например:
    set TAXI_TEST_DB=postgresql://postgres@127.0.0.1:5432/taxi_test
    python -m pytest tests
Без TAXI_TEST_DB тесты с базой пропускаются.
"""
import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DSN = os.environ.get('TAXI_TEST_DB')
PASSENGER = 7_000_000_001  # больше 2^31: нужен BIGINT
DRIVER = 7_000_000_002
DRIVER2 = 7_000_000_003

needs_db = pytest.mark.skipif(not DSN, reason='TAXI_TEST_DB не задан')


@pytest.fixture()
def app(monkeypatch, tmp_path):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN_2', '123456:TEST')
    monkeypatch.setenv('YANDEX_GEOCODER_API_KEY', '')
    if DSN:
        url = urlparse(DSN)
        monkeypatch.setenv('DB_HOST', url.hostname)
        monkeypatch.setenv('DB_PORT', str(url.port or 5432))
        monkeypatch.setenv('DB_USER', url.username or 'postgres')
        monkeypatch.setenv('DB_PASSWORD', url.password or '')
        monkeypatch.setenv('DB_NAME', url.path.lstrip('/'))
    for name in ('app', 'config', 'database', 'geocoder', 'keyboard'):
        sys.modules.pop(name, None)
    app = importlib.import_module('app')
    if DSN:
        app.database._execute('DROP TABLE IF EXISTS users, user_taxi, orders, language, taxi_online, photo_base;')
        app.database.init_db()
    sent = []
    for method in ('send_message', 'answer_callback_query', 'delete_message', 'register_next_step_handler'):
        monkeypatch.setattr(app.bot, method, lambda *a, _m=method, **kw: sent.append((_m, a, kw)) or SimpleNamespace(chat=SimpleNamespace(id=0)))
    monkeypatch.setattr(app, 'PHOTOS_DIR', tmp_path / 'photos')
    app.sent = sent
    return app


def msg(user_id, text=None, location=None, contact=None, photo=None, first_name='Иван'):
    return SimpleNamespace(text=text, location=location, contact=contact, photo=photo, message_id=10,
                           chat=SimpleNamespace(id=user_id),
                           from_user=SimpleNamespace(id=user_id, first_name=first_name, full_name=first_name))


def loc(lat, lon):
    return SimpleNamespace(latitude=lat, longitude=lon)


def texts_to(app, chat_id):
    return [kw.get('text', a[1] if len(a) > 1 else None)
            for m, a, kw in app.sent if m == 'send_message' and (kw.get('chat_id', a[0] if a else None) == chat_id)]


def next_steps(app):
    return [a[1].__name__ for m, a, _ in app.sent if m == 'register_next_step_handler']


def cb(app, user_id, data):
    app.inline_buttons(SimpleNamespace(id='1', data=data,
                                       message=SimpleNamespace(chat=SimpleNamespace(id=user_id), message_id=5)))


def register_driver(app, driver_id, name='Пётр'):
    app.database.registered_user(driver_id, '+998901112233', name)
    app.database.registered_taxis(driver_id, '+998901112233', 'Cobalt', '01A123BC', name)


# ---------- без базы ----------

def test_maps_link_is_lat_lon(app):
    assert app.maps_link(69.28, 41.31) == 'https://maps.google.com/?q=41.31,69.28'


def test_distance_is_symmetric_and_reasonable(app):
    d = app.distance_m(69.28, 41.31, 69.29, 41.32)
    assert d == app.distance_m(69.29, 41.32, 69.28, 41.31)
    assert 1000 < d < 2000


def test_name_is_escaped_in_greeting(app, monkeypatch):
    monkeypatch.setattr(app.database, 'check_user', lambda _id: False)
    app.process_start_command(msg(1, '/start', first_name='<b>x</b>'))
    assert '&lt;b&gt;x&lt;/b&gt;' in texts_to(app, 1)[0]


def test_geocoder_without_key_returns_none(app):
    assert app.coords_to_address(69.28, 41.31) is None
    assert app.address(69.28, 41.31) == '41.31000, 69.28000'


# ---------- с базой ----------

@needs_db
def test_init_db_migrates_old_integer_schema(app):
    db = app.database
    db._execute('DROP TABLE users, user_taxi, orders, language, taxi_online, photo_base;')
    db._execute('CREATE TABLE users (tg_id INTEGER, phone_number TEXT, name VARCHAR(30), reg_date DATE);')
    db._execute('CREATE TABLE orders(pr_id SERIAL PRIMARY KEY, phone VARCHAR(100), longitude_start VARCHAR(100), '
                'latitude_start VARCHAR(100), longitude_end VARCHAR (100), latitude_end VARCHAR (100), price INTEGER, '
                'length_way INTEGER, time_way INTEGER, teg_id INTEGER, new_order VARCHAR(10));')
    db.init_db()
    db.init_db()
    db.registered_user(PASSENGER, '+1', 'x' * 60)
    assert db.check_user(PASSENGER)
    columns = dict(db._execute("SELECT column_name, data_type FROM information_schema.columns "
                               "WHERE table_name='orders';", fetch='all'))
    assert columns['teg_id'] == 'bigint' and columns['taxi_id'] == 'bigint'


@needs_db
def test_connections_are_closed(app):
    db = app.database
    before = db._execute('SELECT count(*) FROM pg_stat_activity WHERE datname = current_database();', fetch='one')[0]
    for _ in range(30):
        db.check_user(PASSENGER)
    after = db._execute('SELECT count(*) FROM pg_stat_activity WHERE datname = current_database();', fetch='one')[0]
    assert after <= before


@needs_db
def test_language_update_changes_only_one_user(app):
    app.database.language_insert(PASSENGER, 'ru')
    app.database.language_insert(DRIVER, 'ru')
    app.language_button(msg(PASSENGER, 'uz'))
    assert app.database.language_select(PASSENGER) == ('uz',)
    assert app.database.language_select(DRIVER) == ('ru',)


@needs_db
def test_passenger_order_flow_with_bad_input(app):
    app.database.registered_user(PASSENGER, '+998900000000', 'Иван')
    cb(app, PASSENGER, 'order')
    app.geo_location(msg(PASSENGER, 'текст вместо геолокации'), '+998900000000')
    assert next_steps(app)[-1] == 'geo_location'

    app.geo_location(msg(PASSENGER, location=loc(41.31, 69.28)), '+998900000000')
    app.where_go(msg(PASSENGER, location=loc(41.32, 69.29)), '+998900000000', 69.28, 41.31)
    app.price_way(msg(PASSENGER, 'сто'), '+998900000000', 69.28, 41.31, 69.29, 41.32)
    assert next_steps(app)[-1] == 'price_way'
    app.price_way(msg(PASSENGER, '-5'), '+998900000000', 69.28, 41.31, 69.29, 41.32)
    assert next_steps(app)[-1] == 'price_way'
    app.price_way(msg(PASSENGER, '25 000'), '+998900000000', 69.28, 41.31, 69.29, 41.32)
    orders = app.database.get_order(PASSENGER)
    assert len(orders) == 1 and orders[0][6] == 25000 and orders[0][10] == 'at work'


@needs_db
def test_text_address_is_geocoded(app, monkeypatch):
    monkeypatch.setattr(app, 'addess_to_coords', lambda text: '69.29 41.32')
    app.where_go(msg(PASSENGER, 'Ташкент, Амир Темур 1'), '+1', 69.28, 41.31)
    assert next_steps(app)[-1] == 'price_way'


@needs_db
def test_only_one_driver_gets_the_order_and_html_is_escaped(app):
    app.database.registered_user(PASSENGER, '+998900000000', 'Иван')
    pr_id = app.database.add_orders('+998900000000', 69.28, 41.31, 69.29, 41.32, 20000, 1400, 2, PASSENGER)
    register_driver(app, DRIVER, name='<a href="http://evil">Пётр</a>')
    register_driver(app, DRIVER2)

    app.get_location_taxi(msg(DRIVER, location=loc(41.311, 69.281)))
    app.get_location_taxi(msg(DRIVER2, location=loc(41.311, 69.281)))
    app.order_start(msg(DRIVER, str(pr_id)), [pr_id])
    app.order_start(msg(DRIVER2, str(pr_id)), [pr_id])

    passenger_msgs = texts_to(app, PASSENGER)
    assert len(passenger_msgs) == 1
    assert '<a href="http://evil">' not in passenger_msgs[0] and '&lt;a href=' in passenger_msgs[0]
    assert '+998901112233' in passenger_msgs[0]  # телефон водителя, а не марка машины
    assert any('уже принял другой водитель' in t for t in texts_to(app, DRIVER2))


@needs_db
def test_far_orders_are_skipped_but_near_ones_after_them_are_shown(app):
    app.database.add_orders('+1', 60.0, 50.0, 60.1, 50.1, 1000, 1, 1, PASSENGER)  # далеко
    near = app.database.add_orders('+2', 69.28, 41.31, 69.29, 41.32, 1000, 1, 1, PASSENGER + 10)
    register_driver(app, DRIVER)
    app.get_location_taxi(msg(DRIVER, location=loc(41.311, 69.281)))
    shown = [t for t in texts_to(app, DRIVER) if 'Заказ №' in t]
    assert len(shown) == 1 and f'№{near}' in shown[0]


@needs_db
def test_cancel_keeps_history_and_notifies_driver(app):
    db = app.database
    done = db.add_orders('+1', 69.28, 41.31, 69.29, 41.32, 1000, 1, 1, PASSENGER)
    db._execute("UPDATE orders SET new_order='done' WHERE pr_id=%s", (done,))
    active = db.add_orders('+1', 69.28, 41.31, 69.29, 41.32, 1000, 1, 1, PASSENGER)
    db.take_order(active, DRIVER)
    cb(app, PASSENGER, 'no_start')
    assert [o[0] for o in db.get_order(PASSENGER)] == [done]
    assert any('отменил' in t for t in texts_to(app, DRIVER))


@needs_db
def test_non_driver_cannot_go_online_and_counter_works(app):
    cb(app, PASSENGER, 'start')
    assert app.database.count_online_taxis() == 0
    register_driver(app, DRIVER)
    cb(app, DRIVER, 'start')
    cb(app, DRIVER, 'start')
    cb(app, PASSENGER, 'taxis')
    assert 'Онлайн таксистов: 1' in texts_to(app, PASSENGER)[-1]
    cb(app, DRIVER, 'finish')
    assert app.database.count_online_taxis() == 0


@needs_db
def test_car_photo_is_saved_under_numeric_id(app, monkeypatch):
    app.database.registered_user(DRIVER, '+1', '..\\..\\evil')
    monkeypatch.setattr(app.bot, 'get_file', lambda file_id: SimpleNamespace(file_path='photos/file_1.jpg'))
    monkeypatch.setattr(app.bot, 'download_file', lambda path: b'jpeg-bytes')
    photo = [SimpleNamespace(file_id='AAA', file_unique_id='uniq1')]
    app.photo_car(msg(DRIVER, photo=photo, first_name='..\\..\\evil'), '+1', '01A123BC', 'Cobalt')
    saved = app.PHOTOS_DIR / str(DRIVER) / 'uniq1.jpg'
    assert saved.read_bytes() == b'jpeg-bytes'
    assert app.database.check_user_taxis(DRIVER)


@needs_db
def test_taxi_registration_retry_keeps_phone(app):
    app.get_number_car(msg(DRIVER, 'x' * 30), '+1')
    step = [a for m, a, _ in app.sent if m == 'register_next_step_handler'][-1]
    assert step[1].__name__ == 'get_number_car' and step[2] == '+1'
