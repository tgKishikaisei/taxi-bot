"""
this is my code
"""
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove


def inline_menu_button():
    """

    :return:
    """
    button = InlineKeyboardMarkup(row_width=2)

    order = InlineKeyboardButton(text='Новая поездка', callback_data='order')
    job = InlineKeyboardButton(text='Работа', callback_data='job')
    taxis = InlineKeyboardButton(text='Таксисты', callback_data='taxis')
    trips = InlineKeyboardButton(text='Поездки', callback_data='trips')

    button.add(order, job, taxis, trips)

    return button


def inline_menu_taxi():
    """

    :return:
    """
    button = InlineKeyboardMarkup(row_width=2)

    start = InlineKeyboardButton(text='Начать работу', callback_data='start')
    finish = InlineKeyboardButton(text='Закончить', callback_data='finish')

    button.add(start, finish)

    return button


def taxi_started_user():
    """

    :return:
    """
    button = InlineKeyboardMarkup(row_width=2)

    start_user = InlineKeyboardButton(text='Такси приехал', callback_data='start_user')
    no_start = InlineKeyboardButton(text='Отменить', callback_data='no_start')

    button.add(start_user,no_start)

    return button


def taxi_finished_user():
    """

    :return:
    """
    button = InlineKeyboardMarkup(row_width=2)

    finish_user = InlineKeyboardButton(text='Приехал', callback_data='finish_user')
    no_finished = InlineKeyboardButton(text='Не приехал', callback_data='no_finished')

    button.add(no_finished, finish_user)

    return button


def language():
    """

    :return:
    """
    button = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)

    uz = KeyboardButton('uz')
    ru = KeyboardButton('ru')

    button.add(uz, ru)

    return button


def location_keyboard():
    """

    :return:
    """

    button_location = KeyboardButton(text="🌐 Определить местоположение", request_location=True)

    keyboard_location = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)

    keyboard_location.add(button_location)
    # Выход из сценария заказа
    keyboard_location.add(KeyboardButton(text='Отмена'))

    return keyboard_location


def passengers_or_taxis():
    """

    :return:
    """
    button = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)

    passenger = KeyboardButton('Пассажир')
    taxis = KeyboardButton('Таксист')

    button.add(passenger, taxis)

    return button


def phone_number_kb():
    """

    :return:
    """
    button = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)

    number = KeyboardButton('Поделиться контактом', request_contact=True)

    button.add(number)

    return button


def order_get_started():
    """

    :return:
    """
    button = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)

    yes = KeyboardButton('Да')
    no = KeyboardButton('Нет')

    button.add(yes, no)

    return button


