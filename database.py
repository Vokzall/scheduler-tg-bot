# database.py
import sqlite3
import logging
from config import Config

logger = logging.getLogger(__name__)

def init_db():
    con = sqlite3.connect(Config.DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
    cur = con.cursor()
    
    # Создание таблицы напоминаний с использованием параметризованных запросов
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT,
            scheduled_iso TEXT NOT NULL,
            lead_minutes INTEGER NOT NULL,
            sent INTEGER DEFAULT 0,
            created_iso TEXT NOT NULL
        )
    """)
    
    # Создание таблицы задач с использованием параметризованных запросов
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            day_iso TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_iso TEXT NOT NULL,
            completed_iso TEXT
        )
    """)
    
    try:
        cur.execute("ALTER TABLE tasks ADD COLUMN original_day_iso TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        # Поле уже существует
        pass
    
    con.commit(); con.close()
    logger.info("Database initialized")

def get_connection():
    """Возвращает безопасное соединение с базой данных"""
    return sqlite3.connect(
        Config.DB_PATH, 
        detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES,
        timeout=15  # Таймаут для избежания блокировок
    )

def execute_sql(sql, params=None):
    """Безопасное выполнение SQL-запроса"""
    try:
        with get_connection() as con:
            cur = con.cursor()
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            con.commit()
            return cur
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        raise