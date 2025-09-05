import logging
from telegram import Bot
from config import Config

logger = logging.getLogger(__name__)

async def send_maintenance_notification():
    try:
        bot = Bot(token=Config.TOKEN)
        await bot.send_message(
            chat_id=Config.ADMIN_ID,
            text="⚠️🚧 Внимание! Бот будет остановлен для технического обслуживания. "
                 "Пользователи временно не смогут пользоваться сервисом. "
                 "Приносим извинения за неудобства! 🛠️⏳"
        )
    except Exception as e:
        logger.error(f"Failed to send maintenance notification: {e}")