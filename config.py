import os as _os
from pathlib import Path as _Path

# Секреты берутся из .env рядом с этим файлом.
_env_file = _Path(__file__).with_name(".env")
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        if "=" in _line and not _line.lstrip().startswith("#"):
            _key, _value = _line.split("=", 1)
            _os.environ.setdefault(_key.strip(), _value.strip().strip('"').strip("'"))

# Данные для подключения
USER = _os.environ.get("DB_USER", "postgres")
PASSWORD = _os.environ.get("DB_PASSWORD", "")
HOST = _os.environ.get("DB_HOST", "localhost")
PORT = _os.environ.get("DB_PORT", "5432")
DATABASE = _os.environ.get("DB_NAME", "taxi")

API_TOKEN = _os.environ.get("TELEGRAM_BOT_TOKEN_2", "")

YANDEX_GEOCODER_API_KEY = _os.environ.get("YANDEX_GEOCODER_API_KEY", "")
