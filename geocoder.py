"""Геокодер Яндекса: координаты <-> адрес.

Ключ берётся из .env, запрос идёт с таймаутом, адрес кодируется в параметрах
запроса, URL с ключом в лог не попадает. Ненайденный адрес не роняет бота.
"""
import logging

import requests

from config import YANDEX_GEOCODER_API_KEY

log = logging.getLogger(__name__)

GEOCODER_URL = "https://geocode-maps.yandex.ru/1.x/"
TIMEOUT = 10


def _first_geo_object(geocode):
    if not YANDEX_GEOCODER_API_KEY:
        return None
    try:
        response = requests.get(GEOCODER_URL, timeout=TIMEOUT, params={
            "apikey": YANDEX_GEOCODER_API_KEY,
            "geocode": geocode,
            "format": "json",
        })
        response.raise_for_status()
        members = response.json()["response"]["GeoObjectCollection"]["featureMember"]
    except (requests.RequestException, ValueError, KeyError) as error:
        # Только тип ошибки и статус: в тексте исключения requests есть URL с ключом
        status = getattr(getattr(error, "response", None), "status_code", None)
        log.warning("Геокодер недоступен: %s (HTTP %s)", type(error).__name__, status)
        return None
    return members[0]["GeoObject"] if members else None


def coords_to_address(x, y):
    """Адрес по координатам (x — долгота, y — широта) или None."""
    toponym = _first_geo_object(f"{x},{y}")
    return toponym["metaDataProperty"]["GeocoderMetaData"]["text"] if toponym else None


def addess_to_coords(address):
    """Строка «долгота широта» по адресу или None."""
    toponym = _first_geo_object(address)
    return toponym["Point"]["pos"] if toponym else None
