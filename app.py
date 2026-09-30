"""Бот такси: пассажиры создают заказы, таксисты принимают ближайшие.

- пользовательский текст (имя, марка и номер машины, адрес) экранируется перед parse_mode='HTML';
- фото машины хранится в photos/<tg_id>/ рядом с ботом;
- ссылки Google Maps строятся как «широта,долгота»;
- поиск заказов не блокирует поток бота паузами;
- ввод текста вместо геолокации или цены не роняет сценарий.
"""
import html
import logging
import math
from pathlib import Path

import telebot
from telebot import types
from telebot.types import ReplyKeyboardRemove

import database
import keyboard
from config import API_TOKEN
from geocoder import addess_to_coords, coords_to_address

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
log = logging.getLogger('taxibot')

bot = telebot.TeleBot(API_TOKEN)

PHOTOS_DIR = Path(__file__).with_name('photos')
SEARCH_RADIUS_M = 15000
MAX_ORDERS_SHOWN = 10
AVERAGE_SPEED_KMH = 40
MAX_PRICE = 10_000_000
CANCEL_WORDS = ('/start', '/cancel', 'Отмена')


def esc(value):
    return html.escape(str(value))


def is_cancel(message):
    return message.text in CANCEL_WORDS


def distance_m(lon1, lat1, lon2, lat2):
    """Приближённое расстояние в метрах (как в исходной версии, для городских расстояний)."""
    x = math.cos(math.radians((lat1 + lat2) / 2))
    dx = abs(lon1 - lon2) * 111000 * x
    dy = abs(lat1 - lat2) * 111000
    return round(math.sqrt(dx * dx + dy * dy))


def maps_link(lon, lat):
    # Google Maps ждёт «широта,долгота»
    return f'https://maps.google.com/?q={lat},{lon}'


def address(lon, lat):
    return coords_to_address(lon, lat) or f'{float(lat):.5f}, {float(lon):.5f}'


def order_text(order, title, links=False):
    pr_id, _, lon_s, lat_s, lon_e, lat_e, price, length_way, time_way = order[:9]
    text = f'<i><b>{esc(title)} №{pr_id}.</b></i>\n\n<i><b>Начальная точка:</b></i> {esc(address(lon_s, lat_s))}'
    if links:
        text += f'\n\n<a href="{esc(maps_link(lon_s, lat_s))}">Начальная точка ➤</a>'
    text += f'\n\n<i><b>Конечная точка:</b></i> {esc(address(lon_e, lat_e))}'
    if links:
        text += f'\n\n<a href="{esc(maps_link(lon_e, lat_e))}">Конечная точка ➤</a>'
    text += (f'\n\n<i><b>Расстояние:</b></i> {length_way} м'
             f'\n\n<i><b>Время пути:</b></i> {time_way} мин'
             f'\n\n<b>Цена:</b> {price} sum')
    return text


def safe_delete(chat_id, message_id):
    # Сообщение могло быть уже удалено или быть старше 48 часов
    try:
        bot.delete_message(chat_id=chat_id, message_id=message_id)
    except telebot.apihelper.ApiException:
        pass


def send_menu(chat_id, text='Выберите пункт меню'):
    bot.send_message(chat_id, text=text, reply_markup=keyboard.inline_menu_button())


def ask_phone(message, next_step, text=None):
    bot.send_message(chat_id=message.chat.id,
                     text=text or f'Привет <b>{esc(message.from_user.first_name)}</b>, рад тебя видеть. '
                                  f'Пожалуйста, отправьте мне свой номер',
                     parse_mode='HTML', reply_markup=keyboard.phone_number_kb())
    bot.register_next_step_handler(message, next_step)


def own_contact(message):
    # Принимаем только свой контакт, не пересланный
    return message.contact is not None and message.contact.user_id == message.from_user.id


# ---------- Регистрация пассажира ----------

@bot.message_handler(commands=['start'])
def process_start_command(message: types.Message):
    if database.check_user(message.chat.id):
        bot.send_message(message.chat.id, text='Выберите что вам нужно', reply_markup=keyboard.inline_menu_button())
    else:
        ask_phone(message, get_phone)


def get_phone(message: types.Message):
    if own_contact(message):
        if not database.check_user(message.chat.id):
            database.registered_user(tg_id=message.chat.id, phone_number=message.contact.phone_number,
                                     name=message.from_user.full_name)
        bot.send_message(chat_id=message.chat.id, text='Вы успешно зарегистрированы как пассажир',
                         reply_markup=ReplyKeyboardRemove())
        send_menu(message.chat.id, 'Выберите пункт с меню')
    else:
        ask_phone(message, get_phone, 'Пожалуйста, отправьте свой номер кнопкой ниже')


# ---------- Регистрация таксиста ----------

def get_number_taxi(message: types.Message):
    if own_contact(message):
        phone_number = message.contact.phone_number
        if not database.check_user(message.chat.id):
            database.registered_user(tg_id=message.chat.id, phone_number=phone_number,
                                     name=message.from_user.full_name)
        ask_car_number(message, phone_number)
    elif is_cancel(message):
        send_menu(message.chat.id)
    else:
        ask_phone(message, get_number_taxi, 'Пожалуйста, отправьте свой номер кнопкой ниже')


def ask_car_number(message, phone_number):
    bot.send_message(chat_id=message.chat.id, text='Отправьте номер машины (/cancel — отмена)',
                     reply_markup=ReplyKeyboardRemove())
    bot.register_next_step_handler(message, get_number_car, phone_number)


def get_number_car(message: types.Message, telephone_number):
    if is_cancel(message):
        send_menu(message.chat.id)
        return
    number_car = (message.text or '').strip()
    if not 1 <= len(number_car) <= 20:
        bot.send_message(chat_id=message.chat.id, text='Пожалуйста, отправьте номер машины текстом (до 20 символов)')
        bot.register_next_step_handler(message, get_number_car, telephone_number)
        return
    bot.send_message(chat_id=message.chat.id, text='Теперь напишите название машины')
    bot.register_next_step_handler(message, name_car, telephone_number, number_car)


def name_car(message: types.Message, telephone_number, number_car):
    if is_cancel(message):
        send_menu(message.chat.id)
        return
    car = (message.text or '').strip()
    if not 1 <= len(car) <= 64:
        bot.send_message(chat_id=message.chat.id, text='Напишите модель машины (до 64 символов)')
        bot.register_next_step_handler(message, name_car, telephone_number, number_car)
        return
    bot.send_message(chat_id=message.chat.id, text='Отправьте фото машины')
    bot.register_next_step_handler(message, photo_car, telephone_number, number_car, car)


def photo_car(message: types.Message, telephone_number, numbers_car, name_car_message):
    if is_cancel(message):
        send_menu(message.chat.id)
        return
    if not message.photo:
        bot.send_message(chat_id=message.chat.id, text='Нужна фотография машины')
        bot.register_next_step_handler(message, photo_car, telephone_number, numbers_car, name_car_message)
        return

    photo = message.photo[-1]
    file_info = bot.get_file(file_id=photo.file_id)
    extension = Path(file_info.file_path).suffix.lower()
    if extension not in ('.jpg', '.jpeg', '.png', '.webp'):
        extension = '.jpg'

    # Папка по числовому ID: имя пользователя в пути позволяло писать файлы куда угодно
    folder = PHOTOS_DIR / str(message.chat.id)
    folder.mkdir(parents=True, exist_ok=True)
    src = folder / f'{photo.file_unique_id}{extension}'
    src.write_bytes(bot.download_file(file_info.file_path))

    database.add_file_photo_base(str(src), message.chat.id, str(folder))
    if not database.check_user_taxis(message.chat.id):
        database.registered_taxis(tg_id=message.chat.id, phone_number=telephone_number, car_name=name_car_message,
                                  number_car=numbers_car, name=message.from_user.full_name)

    bot.send_message(chat_id=message.chat.id, text='Вы зарегистрированы как таксист')
    bot.send_message(chat_id=message.chat.id, text='Меню таксиста', reply_markup=keyboard.inline_menu_taxi())


# ---------- Команды и текстовые кнопки ----------

@bot.message_handler(commands=['choice'])
def passenger_or_taxis(message: types.Message):
    bot.send_message(chat_id=message.chat.id, text='Хотите изменить, выберите ПАССАЖИР/ТАКСИСТ',
                     reply_markup=keyboard.passengers_or_taxis())


@bot.message_handler(commands=['language'])
def language_choice(message: types.Message):
    if database.language_select(message.from_user.id) is None:
        database.language_insert(message.from_user.id, 'ru')
    bot.send_message(message.chat.id, text='Выберите язык, на котором будут отображаться сообщения',
                     reply_markup=keyboard.language())


@bot.message_handler(content_types=['text'])
def language_button(message: types.Message):
    if message.text in ('ru', 'uz'):
        # Язык меняется только у текущего пользователя
        database.language_update(message.from_user.id, message.text)
        bot.send_message(chat_id=message.chat.id,
                         text='Теперь все на русском' if message.text == 'ru' else 'Теперь все на узбекском',
                         reply_markup=ReplyKeyboardRemove())
        send_menu(message.chat.id, 'Выберите пункт с меню')

    elif message.text == 'Пассажир':
        safe_delete(message.chat.id, message.message_id - 1)
        bot.send_message(chat_id=message.chat.id, text='Вы пассажир', reply_markup=ReplyKeyboardRemove())
        send_menu(message.chat.id)

    elif message.text == 'Таксист':
        if database.check_user_taxis(message.from_user.id):
            safe_delete(message.chat.id, message.message_id - 1)
            bot.send_message(chat_id=message.chat.id, text='Вы таксист', reply_markup=keyboard.inline_menu_taxi())
        else:
            bot.send_message(chat_id=message.chat.id, text='Вы должны пройти регистрацию на таксиста')
            phone = database.get_user_phone_number(message.from_user.id)
            if phone:
                # Номер уже есть — сразу спрашиваем машину
                ask_car_number(message, phone[0])
            else:
                ask_phone(message, get_number_taxi)

    elif message.text == 'Мои поездки':
        show_trips(message.chat.id)


def show_trips(chat_id):
    orders = database.get_order(user_id=chat_id)
    if not orders:
        bot.send_message(chat_id=chat_id, text='У вас пока нет поездок')
        return
    for order in orders[:MAX_ORDERS_SHOWN]:
        bot.send_message(chat_id=chat_id, text=order_text(order, 'Заказ'), parse_mode='HTML',
                         disable_web_page_preview=True)


# ---------- Заказ поездки (пассажир) ----------

def geo_location(message: types.Message, phone):
    if is_cancel(message):
        bot.send_message(message.chat.id, 'Заказ отменён', reply_markup=ReplyKeyboardRemove())
        send_menu(message.chat.id)
        return
    if not message.location:
        bot.send_message(message.chat.id, 'Отправьте геолокацию кнопкой ниже',
                         reply_markup=keyboard.location_keyboard())
        bot.register_next_step_handler(message, geo_location, phone)
        return

    latitude, longitude = message.location.latitude, message.location.longitude
    bot.send_message(message.chat.id, address(longitude, latitude), reply_markup=ReplyKeyboardRemove())
    mess = bot.send_message(message.chat.id, '<b>Куда едем?</b>\nОтправьте геолокацию или напишите адрес',
                            parse_mode='HTML', reply_markup=keyboard.location_keyboard())
    bot.register_next_step_handler(mess, where_go, phone, longitude, latitude)


def where_go(message: types.Message, phone, longitude_start, latitude_start):
    if is_cancel(message):
        bot.send_message(message.chat.id, 'Заказ отменён', reply_markup=ReplyKeyboardRemove())
        send_menu(message.chat.id)
        return

    coords = None
    if message.location:
        coords = (message.location.longitude, message.location.latitude)
    elif message.text:
        # Куда едем: принимаем и геолокацию, и адрес текстом
        pos = addess_to_coords(message.text[:200])
        if pos:
            lon, lat = pos.split()
            coords = (float(lon), float(lat))
    if coords is None:
        bot.send_message(message.chat.id, 'Не удалось определить адрес. Отправьте геолокацию или другой адрес',
                         reply_markup=keyboard.location_keyboard())
        bot.register_next_step_handler(message, where_go, phone, longitude_start, latitude_start)
        return

    mess = bot.send_message(chat_id=message.chat.id, text='Укажите желаемую цену в sum.',
                            reply_markup=ReplyKeyboardRemove())
    bot.register_next_step_handler(mess, price_way, phone, longitude_start, latitude_start, *coords)


def price_way(message: types.Message, phone, longitude_start, latitude_start, longitude_end, latitude_end):
    if is_cancel(message):
        send_menu(message.chat.id, 'Заказ отменён')
        return
    text = (message.text or '').replace(' ', '')
    # Цена — целое положительное число
    if not text.isdigit() or not 0 < int(text) <= MAX_PRICE:
        bot.send_message(message.chat.id, 'Цена — целое число в sum, например 25000')
        bot.register_next_step_handler(message, price_way, phone, longitude_start, latitude_start,
                                       longitude_end, latitude_end)
        return
    price = int(text)

    if database.get_active_order(message.chat.id):
        send_menu(message.chat.id, 'У вас уже есть активный заказ. Отмените его, чтобы создать новый.')
        return

    length_way = distance_m(longitude_start, latitude_start, longitude_end, latitude_end)
    time_way = round(length_way / (AVERAGE_SPEED_KMH * 1000) * 60)

    pr_id = database.add_orders(phone=phone, longitude_start=longitude_start, latitude_start=latitude_start,
                                latitude_end=latitude_end, longitude_end=longitude_end, price=price,
                                length_way=length_way, time_way=time_way, teg_id=message.chat.id)

    order = (pr_id, phone, longitude_start, latitude_start, longitude_end, latitude_end, price, length_way, time_way)
    bot.send_message(message.chat.id, order_text(order, 'Ваш заказ'), parse_mode='HTML',
                     disable_web_page_preview=True, reply_markup=ReplyKeyboardRemove())
    send_menu(message.chat.id, 'Меню')


# ---------- Поиск заказа (таксист) ----------

def get_location_taxi(message: types.Message):
    if is_cancel(message) or not message.location:
        bot.send_message(message.chat.id, 'Поиск отменён', reply_markup=ReplyKeyboardRemove())
        bot.send_message(message.chat.id, 'Меню таксиста', reply_markup=keyboard.inline_menu_taxi())
        return

    latitude, longitude = message.location.latitude, message.location.longitude
    nearby = []
    for order in database.get_order_is_location(database.ORDER_OPEN):
        length = distance_m(longitude, latitude, float(order[2]), float(order[3]))
        if length <= SEARCH_RADIUS_M:
            nearby.append((length, order))
    nearby.sort(key=lambda item: item[0])
    nearby = [order for _, order in nearby[:MAX_ORDERS_SHOWN]]

    if not nearby:
        bot.send_message(chat_id=message.chat.id, text='Извините, пока что нет подходящих заказов',
                         reply_markup=ReplyKeyboardRemove())
        bot.send_message(message.chat.id, 'Меню таксиста', reply_markup=keyboard.inline_menu_taxi())
        return

    for order in nearby:
        bot.send_message(chat_id=message.chat.id, text=order_text(order, 'Заказ', links=True),
                         parse_mode='HTML', disable_web_page_preview=True, reply_markup=ReplyKeyboardRemove())
    bot.send_message(chat_id=message.chat.id, text='Чтобы принять заказ, напишите его номер (/cancel — отмена)')
    bot.register_next_step_handler(message, order_start, [order[0] for order in nearby])


def order_start(message: types.Message, order_ids):
    if is_cancel(message):
        bot.send_message(message.chat.id, 'Меню таксиста', reply_markup=keyboard.inline_menu_taxi())
        return
    text = (message.text or '').strip().lstrip('№')
    if not text.isdigit() or int(text) not in order_ids:
        bot.send_message(chat_id=message.chat.id, text='По этому номеру ничего не нашлось. Напишите номер из списка')
        bot.register_next_step_handler(message, order_start, order_ids)
        return

    info_taxi = database.get_all_taxi(taxi_id=message.chat.id)
    if not info_taxi:
        send_menu(message.chat.id, 'Сначала зарегистрируйтесь как таксист: /choice')
        return

    # Атомарно: второй водитель, выбравший тот же заказ, получит отказ
    order = database.take_order(int(text), message.chat.id)
    if order is None:
        bot.send_message(message.chat.id, 'Этот заказ уже принял другой водитель или пассажир его отменил',
                         reply_markup=keyboard.inline_menu_taxi())
        return

    bot.send_message(chat_id=message.chat.id, text=order_text(order, 'Вы приняли заказ', links=True),
                     parse_mode='HTML', disable_web_page_preview=True, reply_markup=ReplyKeyboardRemove())

    _, taxi_phone, car_name, number_car, taxi_name, _ = info_taxi
    bot.send_message(chat_id=order[9],
                     text=f'Ваш заказ принял {esc(taxi_name)}'
                          f'\n\n<i><b>Номер машины: </b></i>{esc(number_car)}'
                          f'\n\n<i><b>Машина: </b></i>{esc(car_name)}'
                          f'\n\n<i><b>Номер водителя: </b></i>{esc(taxi_phone)}'
                          f'\n\n<i><b>Время в пути: </b></i>{order[8]} мин'
                          f'\n\n<i><b>Расстояние:</b></i> {order[7]} м',
                     parse_mode='HTML', reply_markup=keyboard.taxi_started_user())


# ---------- Инлайн-кнопки ----------

@bot.callback_query_handler(lambda c: c.data)
def inline_buttons(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.message_id
    data = callback_query.data
    bot.answer_callback_query(callback_query.id)

    if data == 'order':
        phone = database.get_user_phone_number(chat_id)
        if not phone:
            bot.send_message(chat_id, 'Сначала зарегистрируйтесь: /start')
            return
        mess = bot.send_message(chat_id=chat_id, text='Отправьте вашу геолокацию.🌐',
                                reply_markup=keyboard.location_keyboard())
        bot.register_next_step_handler(mess, geo_location, phone[0])

    elif data == 'trips':
        safe_delete(chat_id, message_id)
        show_trips(chat_id)
        send_menu(chat_id)

    elif data == 'job':
        safe_delete(chat_id, message_id)
        bot.send_message(chat_id=chat_id, text='Пока что у нас открытых вакансий нет')

    elif data == 'taxis':
        bot.send_message(chat_id=chat_id, text=f'Онлайн таксистов: {database.count_online_taxis()}')

    elif data == 'start':
        # Кнопка только для таксистов
        if not database.check_user_taxis(chat_id):
            bot.send_message(chat_id, 'Сначала зарегистрируйтесь как таксист: /choice')
            return
        database.set_taxi_online(chat_id, True)
        mess = bot.send_message(chat_id=chat_id, text='Отправьте вашу геолокацию.🌐',
                                reply_markup=keyboard.location_keyboard())
        bot.register_next_step_handler(mess, get_location_taxi)

    elif data == 'finish':
        safe_delete(chat_id, message_id)
        database.set_taxi_online(chat_id, False)
        bot.send_message(chat_id=chat_id, text='До встречи')

    elif data == 'start_user':
        safe_delete(chat_id, message_id)
        bot.send_message(chat_id=chat_id, text='Спасибо, мы рады, что выбрали нас',
                         reply_markup=keyboard.taxi_finished_user())

    elif data == 'no_start':
        safe_delete(chat_id, message_id)
        # Отмена удаляет только активный заказ и уведомляет водителя
        for taxi_id in database.cancel_active_orders(chat_id):
            try:
                bot.send_message(taxi_id, 'Пассажир отменил заказ', reply_markup=keyboard.inline_menu_taxi())
            except telebot.apihelper.ApiException:
                log.warning('Не удалось уведомить водителя %s', taxi_id)
        send_menu(chat_id, 'Ваш заказ был удалён')

    elif data == 'finish_user':
        safe_delete(chat_id, message_id)
        database.finish_orders(chat_id)
        bot.send_message(chat_id=chat_id, text='Спасибо, что выбрали нас, хорошего дня')

    elif data == 'no_finished':
        safe_delete(chat_id, message_id)
        bot.send_message(chat_id=chat_id, text='Оставить отзыв или жалобу /support')


if __name__ == '__main__':
    database.init_db()
    log.info('Бот запущен')
    # infinity_polling сам переподключается после ошибок сети
    bot.infinity_polling(timeout=60, skip_pending=True)
