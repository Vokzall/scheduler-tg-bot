#!/usr/bin/env python3
"""
Основной файл бота
"""
import asyncio
import logging
import signal
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from config import Config
import handlers
from database import init_db
from utils import ensure_profile_image
from scheduler import SchedulerManager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(Config.LOG_PATH),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Глобальная переменная для хранения объекта приложения
app_instance = None
scheduler_manager = None

async def send_maintenance_notification():
    """Отправляет уведомление о технических работах"""
    try:
        if app_instance:
            await app_instance.bot.send_message(
                chat_id=Config.ADMIN_ID,
                text="⚠️🚧 Внимание! Бот будет остановлен для технического обслуживания. "
                     "Пользователи временно не смогут пользоваться сервисом. "
                     "Приносим извинения за неудобства! 🛠️⏳"
            )
    except Exception as e:
        logger.error(f"Failed to send maintenance notification: {e}")

async def send_shutdown_notification():
    """Отправляет уведомление об остановке бота"""
    try:
        if app_instance:
            await app_instance.bot.send_message(
                chat_id=Config.ADMIN_ID,
                text="🛑🔌 Бот был остановлен! Сервис временно недоступен. "
                     "Техническая команда уже работает над решением проблемы. "
                     "Приносим извинения за неудобства! ⚠️🔧"
            )
    except Exception as e:
        logger.error(f"Failed to send shutdown notification: {e}")

def register_handlers(app):
    """Регистрация всех обработчиков"""
    app.add_handler(CommandHandler("start", handlers.start_cmd))
    app.add_handler(CommandHandler("stats", handlers.stats_cmd))
    
    app.add_handler(CallbackQueryHandler(handlers.open_calendar_cb, pattern=r"^open_calendar:"))
    app.add_handler(CallbackQueryHandler(handlers.day_selection_cb, pattern=r"^daysel:"))
    app.add_handler(CallbackQueryHandler(handlers.chmonth_cb, pattern=r"^chmonth:"))
    app.add_handler(CallbackQueryHandler(handlers.hoursel_cb, pattern=r"^hoursel:"))
    app.add_handler(CallbackQueryHandler(handlers.minute_select_cb, pattern=r"^minutesel:"))
    app.add_handler(CallbackQueryHandler(handlers.lead_select_cb, pattern=r"^lead:"))
    app.add_handler(CallbackQueryHandler(handlers.confirm_reminder_cb, pattern=r"^confirm_reminder$"))
    
    app.add_handler(CallbackQueryHandler(handlers.today_tasks_cb, pattern=r"^today_tasks$"))
    app.add_handler(CallbackQueryHandler(handlers.add_task_cb, pattern=r"^add_task$"))
    app.add_handler(CallbackQueryHandler(handlers.toggle_task_cb, pattern=r"^toggle_task:"))
    
    # Универсальный обработчик для неизвестных callback
    app.add_handler(CallbackQueryHandler(handlers.unknown_cb))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.text_message_handler))

async def main():
    global app_instance, scheduler_manager
    
    # Инициализация базы данных и изображения профиля
    init_db()
    ensure_profile_image()
    
    # Создание приложения
    app = ApplicationBuilder().token(Config.TOKEN).build()
    app_instance = app
    
    # Регистрация обработчиков
    register_handlers(app)
    
    # Инициализация планировщика
    scheduler_manager = SchedulerManager(app)
    app.scheduler_manager = scheduler_manager 
    
    # Запуск планировщика
    await scheduler_manager.start_scheduler()
    
    # Планирование системных задач
    scheduler_manager.scheduler.add_job(
        scheduler_manager.rollover_pending_tasks,
        trigger="cron",
        hour=0,
        minute=0,
        timezone=Config.TZ
    )
    
    # Загрузка существующих напоминаний
    await scheduler_manager.schedule_existing_reminders()
    
    logger.info("Bot starting...")
    await app.initialize()
    await app.start()
    
    # Уведомление о запуске (только если ADMIN_ID валиден)
    if Config.ADMIN_ID != 0:
        try:
            await app.bot.send_message(
                chat_id=Config.ADMIN_ID,
                text="🤖 Бот успешно запущен и готов к работе! ✅"
            )
        except Exception as e:
            logger.error(f"Failed to send startup notification: {e}")
    else:
        logger.warning("ADMIN_ID is not set, skipping startup notification")
    
    # Настройка обработки сигналов для корректного завершения
    loop = asyncio.get_running_loop()
    for signame in ('SIGINT', 'SIGTERM'):
        loop.add_signal_handler(
            getattr(signal, signame),
            lambda: asyncio.create_task(shutdown(app))
        )
    
    await app.updater.start_polling()
    
    try:
        # Бесконечный цикл работы бота
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown signal received...")
        await shutdown(app)

async def shutdown(app):
    """Корректное завершение работы бота"""
    logger.info("Shutting down...")
    try:
        # Отправляем уведомление об остановке (только если ADMIN_ID валиден)
        if Config.ADMIN_ID != 0:
            await send_shutdown_notification()
        
        # Останавливаем компоненты
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        
        # Останавливаем планировщик
        if scheduler_manager:
            scheduler_manager.scheduler.shutdown()
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)
    finally:
        # Завершаем все асинхронные задачи
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Bot shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception("Fatal error in main")
        try:
            # Попытка отправить уведомление об ошибке
            if Config.ADMIN_ID != 0:
                asyncio.run(send_shutdown_notification())
        except:
            pass