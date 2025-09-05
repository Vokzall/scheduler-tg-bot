# config.py
import os
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()

class Config:
    TOKEN = os.getenv("SCHEDULER_BOT_TOKEN", "")
    ADMIN_ID = int(os.getenv("SCHEDULER_BOT_ADMIN_ID", "0"))
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(BASE_DIR, "scheduler.db")
    LOG_PATH = os.path.join(BASE_DIR, "bot.log")
    PROFILE_PNG = os.path.join(BASE_DIR, "logo.png")
    TZ = "Europe/Moscow"
    
    # Конфигурация безопасности
    SQL_PARAM_STYLE = "named"