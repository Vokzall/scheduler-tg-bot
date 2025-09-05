# utils.py
import os
import logging
from datetime import datetime, date
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from config import Config

logger = logging.getLogger(__name__)

def ensure_profile_image():
    if os.path.exists(Config.PROFILE_PNG): 
        return
    
    img = Image.new("RGB", (512, 512), (40, 120, 200))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 80)
    except Exception:
        font = ImageFont.load_default()
    
    text = "📅 SchedBot"
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        try: 
            w, h = font.getsize(text)
        except Exception: 
            w, h = 200, 50
    
    draw.text(((512 - w) / 2, (512 - h) / 2), text, fill=(255, 255, 255), font=font)
    img.save(Config.PROFILE_PNG)
    logger.info("Generated profile image at %s", Config.PROFILE_PNG)

def user_now():
    return datetime.now(ZoneInfo(Config.TZ))

async def safe_edit_message(message, text=None, reply_markup=None):
    try:
        has_media = bool(
            getattr(message, "photo", None) or 
            getattr(message, "video", None) or 
            getattr(message, "document", None)
        )
        
        if text is None:
            try:
                await message.edit_reply_markup(reply_markup=reply_markup)
                return
            except BadRequest as e:
                if "Message is not modified" in str(e): 
                    return
        else:
            if has_media:
                try:
                    await message.edit_caption(caption=text, reply_markup=reply_markup)
                    return
                except BadRequest as e:
                    if "There is no text in the message to edit" in str(e):
                        await message.reply_text(text, reply_markup=reply_markup)
                        return
                    if "Message is not modified" in str(e): 
                        return
            else:
                try:
                    await message.edit_text(text, reply_markup=reply_markup)
                    return
                except BadRequest as e:
                    if "Message is not modified" in str(e): 
                        return
        
        # Fallback: send new message
        await message.reply_text(text or "", reply_markup=reply_markup)
    except Exception:
        logger.exception("safe_edit_message fallback failed")
        try: 
            await message.reply_text(text or "", reply_markup=reply_markup)
        except Exception: 
            logger.exception("safe_edit_message double fallback failed")

def build_hours_keyboard():
    """Создает клавиатуру со всеми 24 часами на одной странице (4x6)"""
    buttons = []
    # Создаем 6 строк по 4 часа
    for i in range(0, 24, 4):
        row = [
            InlineKeyboardButton(f"{h:02d}🕒", callback_data=f"hoursel:{h}")
            for h in range(i, i + 4)
        ]
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="open_calendar:create_reminder")])
    return InlineKeyboardMarkup(buttons)