from io import BytesIO

import requests
from PIL import Image


def create_static_map_order(coords, path='map_point.png'):  # static map geopos for choose passenger
    response = requests.get("https://static-maps.yandex.ru/1.x/", timeout=10, params={
        "l": "map", "ll": coords, "pt": f"{coords},pm2rdm", "spn": "0.004,0.004",
    })
    response.raise_for_status()
    Image.open(BytesIO(response.content)).save(path)
    return path
