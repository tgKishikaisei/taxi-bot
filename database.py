"""Работа с PostgreSQL.

Что было не так в старой версии:
- соединения не закрывались явно (их закрывал только сборщик мусора CPython),
  и 600 строк кода повторяли одно и то же подключение в каждой функции;
- все функции были объявлены внутри try: если база недоступна при старте,
  модуль импортировался без них, а в finally падал NameError;
- tg_id был INTEGER, а ID Telegram давно больше 2^31;
- language_update менял язык ВСЕМ пользователям (UPDATE без WHERE);
- taxi_online_update обращался к несуществующей таблице popular;
- один заказ могли одновременно принять два водителя.
"""
from contextlib import closing
from datetime import datetime

import psycopg2

import config as sfg

ORDER_OPEN = 'at work'
ORDER_IN_PROGRESS = 'progress'
ORDER_DONE = 'done'


def _connect():
    return psycopg2.connect(user=sfg.USER, password=sfg.PASSWORD, host=sfg.HOST,
                            port=sfg.PORT, dbname=sfg.DATABASE)


def _execute(query, params=(), fetch=None):
    # `with connection` коммитит или откатывает транзакцию, closing() закрывает соединение
    with closing(_connect()) as connection:
        with connection, connection.cursor() as cursor:
            cursor.execute(query, params)
            if fetch == 'one':
                return cursor.fetchone()
            if fetch == 'all':
                return cursor.fetchall()
            return cursor.rowcount


def init_db():
    statements = [
        'CREATE TABLE IF NOT EXISTS users (tg_id BIGINT, phone_number TEXT, name VARCHAR(64), reg_date DATE);',
        'CREATE TABLE IF NOT EXISTS user_taxi (tg_id BIGINT, phone_number TEXT, car_name TEXT, '
        'number_car VARCHAR(20), name VARCHAR(64), reg_date DATE);',
        'CREATE TABLE IF NOT EXISTS orders(pr_id SERIAL PRIMARY KEY, phone VARCHAR(100), '
        'longitude_start VARCHAR(100), latitude_start VARCHAR(100), '
        'longitude_end VARCHAR (100), latitude_end VARCHAR (100), '
        'price INTEGER, length_way INTEGER, time_way INTEGER, teg_id BIGINT, new_order VARCHAR(10));',
        'CREATE TABLE IF NOT EXISTS language(tg_id BIGINT, languages VARCHAR(10));',
        'CREATE TABLE IF NOT EXISTS taxi_online (tg_id BIGINT, online INTEGER, offline INTEGER);',
        'CREATE TABLE IF NOT EXISTS photo_base(file_name VARCHAR, user_id BIGINT, file VARCHAR);',
        # Миграция существующей базы: большие ID Telegram и длинные имена
        'ALTER TABLE users ALTER COLUMN tg_id TYPE BIGINT, ALTER COLUMN name TYPE VARCHAR(64);',
        'ALTER TABLE user_taxi ALTER COLUMN tg_id TYPE BIGINT, ALTER COLUMN name TYPE VARCHAR(64), '
        'ALTER COLUMN number_car TYPE VARCHAR(20);',
        'ALTER TABLE orders ALTER COLUMN teg_id TYPE BIGINT;',
        'ALTER TABLE language ALTER COLUMN tg_id TYPE BIGINT;',
        'ALTER TABLE taxi_online ALTER COLUMN tg_id TYPE BIGINT;',
        'ALTER TABLE photo_base ALTER COLUMN user_id TYPE BIGINT;',
        # Кто из водителей взял заказ: нужно, чтобы сообщить ему об отмене
        'ALTER TABLE orders ADD COLUMN IF NOT EXISTS taxi_id BIGINT;',
    ]
    with closing(_connect()) as connection:
        with connection, connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)


# Регистрация пассажира
def registered_user(tg_id, phone_number, name):
    _execute('INSERT INTO users (tg_id, phone_number, name, reg_date) VALUES (%s, %s, %s, %s);',
             (tg_id, phone_number, name[:64], datetime.now()))


# Регистрация таксиста
def registered_taxis(tg_id, phone_number, car_name, number_car, name):
    _execute('INSERT INTO user_taxi (tg_id, phone_number, car_name, number_car, name, reg_date) '
             'VALUES (%s, %s, %s, %s, %s, %s);',
             (tg_id, phone_number, car_name, number_car, name[:64], datetime.now()))


def check_user_taxis(user_id):
    return _execute('SELECT tg_id FROM user_taxi WHERE tg_id=%s;', (user_id,), fetch='one') is not None


# (tg_id, phone_number, car_name, number_car, name, reg_date) или False
def get_all_taxi(taxi_id):
    return _execute('SELECT tg_id, phone_number, car_name, number_car, name, reg_date '
                    'FROM user_taxi WHERE tg_id=%s;', (taxi_id,), fetch='one') or False


get_all_user_taxi = get_all_taxi


def check_user(user_id):
    return _execute('SELECT tg_id FROM users WHERE tg_id=%s;', (user_id,), fetch='one') is not None


# (phone_number,) или False
def get_user_phone_number(user_id):
    return _execute('SELECT phone_number FROM users WHERE tg_id=%s;', (user_id,), fetch='one') or False


def language_insert(user_id, language):
    _execute('INSERT INTO language (tg_id, languages) VALUES (%s, %s);', (user_id, language))


# (languages,) или None
def language_select(user_id):
    return _execute('SELECT languages FROM language WHERE tg_id=%s;', (user_id,), fetch='one')


def language_update(user_id, language):
    if not _execute('UPDATE language SET languages=%s WHERE tg_id=%s;', (language, user_id)):
        language_insert(user_id, language)


def set_taxi_online(tg_id, online):
    if not _execute('UPDATE taxi_online SET online=%s WHERE tg_id=%s;', (int(online), tg_id)):
        _execute('INSERT INTO taxi_online (tg_id, online, offline) VALUES (%s, %s, 0);', (tg_id, int(online)))


def count_online_taxis():
    return _execute('SELECT COUNT(*) FROM taxi_online WHERE online=1;', fetch='one')[0]


def add_file_photo_base(file_name, user_id, file):
    _execute('INSERT INTO photo_base (file_name, user_id, file) VALUES (%s, %s, %s);', (file_name, user_id, file))


# Все поездки пассажира, новые сверху
def get_order(user_id):
    return _execute('SELECT pr_id, phone, longitude_start, latitude_start, longitude_end, latitude_end, '
                    'price, length_way, time_way, teg_id, new_order FROM orders '
                    'WHERE teg_id=%s ORDER BY pr_id DESC;', (user_id,), fetch='all')


def get_order_is_location(name):
    return _execute('SELECT pr_id, phone, longitude_start, latitude_start, longitude_end, latitude_end, '
                    'price, length_way, time_way, teg_id, new_order FROM orders '
                    'WHERE new_order=%s ORDER BY pr_id;', (name,), fetch='all')


def get_active_order(user_id):
    return _execute('SELECT pr_id FROM orders WHERE teg_id=%s AND new_order IN (%s, %s);',
                    (user_id, ORDER_OPEN, ORDER_IN_PROGRESS), fetch='one')


def add_orders(phone, longitude_start, latitude_start, longitude_end, latitude_end, price, length_way,
               time_way, teg_id, order=ORDER_OPEN):
    return _execute('INSERT INTO orders (phone, longitude_start, latitude_start, longitude_end, latitude_end, '
                    'price, length_way, time_way, teg_id, new_order) '
                    'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING pr_id;',
                    (phone, longitude_start, latitude_start, longitude_end, latitude_end,
                     price, length_way, time_way, teg_id, order), fetch='one')[0]


def take_order(pr_id, taxi_id):
    """Атомарно отдаёт открытый заказ водителю. None, если заказ уже взят или отменён."""
    return _execute('UPDATE orders SET new_order=%s, taxi_id=%s WHERE pr_id=%s AND new_order=%s '
                    'RETURNING pr_id, phone, longitude_start, latitude_start, longitude_end, latitude_end, '
                    'price, length_way, time_way, teg_id, new_order;',
                    (ORDER_IN_PROGRESS, taxi_id, pr_id, ORDER_OPEN), fetch='one')


def cancel_active_orders(tg_id):
    """Удаляет только текущие заказы пассажира, история поездок остаётся.

    Возвращает ID водителей, которые уже ехали к пассажиру.
    """
    rows = _execute('DELETE FROM orders WHERE teg_id=%s AND new_order IN (%s, %s) RETURNING taxi_id;',
                    (tg_id, ORDER_OPEN, ORDER_IN_PROGRESS), fetch='all')
    return [taxi_id for (taxi_id,) in rows if taxi_id]


def finish_orders(tg_id):
    _execute('UPDATE orders SET new_order=%s WHERE teg_id=%s AND new_order=%s;',
             (ORDER_DONE, tg_id, ORDER_IN_PROGRESS))
