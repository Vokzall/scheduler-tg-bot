import asyncio
import logging
import calendar
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import ContextTypes
from config import Config
from utils import ensure_profile_image, user_now, safe_edit_message, build_hours_keyboard
from database import execute_sql, get_connection

logger = logging.getLogger(__name__)

class Messages:
    # Приветственные сообщения
    @staticmethod
    def welcome(user_name: str) -> str:
        return f"Привет, {user_name}! Я — Scheduler Bot 📅\nИспользуй меню рядом со строкой ввода для управления."
    
    @staticmethod
    def start_actions() -> str:
        return "Выбери действие:"
    
    # Сообщения для задач
    @staticmethod
    def no_tasks() -> str:
        return "📋 Сегодня задач пока нет!"
    
    @staticmethod
    def task_list_header() -> str:
        return "📋 Ваши задачи на сегодня:"
    
    @staticmethod
    def task_item(completed: bool, description: str, date_info: str = "") -> str:
        emoji = "✅" if completed else "❌"
        return f"{emoji} {description}{date_info}"
    
    # Напоминания
    @staticmethod
    def reminder_created(title: str, time_str: str, lead: int) -> str:
        return (
            f"✅ Напоминание создано!\n\n"
            f"📝 Событие: {title}\n"
            f"📅 Дата: {time_str}\n"
            f"Отправлю напоминание за {lead} мин."
        )
    
    @staticmethod
    def no_reminders() -> str:
        return "📋 У вас нет активных напоминаний!"
    
    @staticmethod
    def reminders_list_header() -> str:
        return "📋 Ваши активные напоминания:"
    
    @staticmethod
    def reminder_item(title: str, time_str: str, lead: int) -> str:
        return f"• {title} - {time_str} (напомнить за {lead} мин.)"
    
    # Технические сообщения
    @staticmethod
    def maintenance_notification() -> str:
        return (
            "⚠️🚧 Внимание! Бот временно не работает, ведутся технические работы. "
            "Мы скоро вернемся с улучшениями! 🛠️⏳ Приносим извинения за неудобства."
        )
    
    @staticmethod
    def bot_about() -> str:
        return (
            "ℹ️ Бот-напоминалка с функциями:\n\n"
            "• Управление задачами на день ✅\n"
            "• Напоминания о событиях ⏰\n"
            "• История выполненных задач 📊"
        )

# UI keyboard (persistent)
REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("📅 Создать напоминание"), KeyboardButton("✅ Список дел на сегодня")],
     [KeyboardButton("📊 Просмотреть задачи по дате"), KeyboardButton("📋 Мои напоминания")],
     [KeyboardButton("ℹ️ О боте")]],
    resize_keyboard=True
)

def build_month_keyboard(year, month, mode="view", disable_past=True):
    cal = calendar.Calendar(firstweekday=0)
    today = datetime.now(ZoneInfo(Config.TZ)).date()
    kb = []
    
    # Add emoji to title based on mode
    emoji = "📅"
    if mode == "create_reminder": emoji = "⏰"
    elif mode == "view_tasks": emoji = "✅"
    
    kb.append([InlineKeyboardButton(f"{emoji} {calendar.month_name[month]} {year}", callback_data="noop")])
    kb.append([InlineKeyboardButton(w, callback_data="noop") for w in ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]])
    
    for week in cal.monthdayscalendar(year, month):
        row = []
        for d in week:
            if d == 0: 
                row.append(InlineKeyboardButton(" ", callback_data="noop"))
            else:
                dt = date(year, month, d)
                if disable_past and dt < today:
                    row.append(InlineKeyboardButton("·", callback_data="noop"))
                else:
                    today_indicator = "🟢" if dt == today else ""
                    row.append(InlineKeyboardButton(
                        f"{today_indicator}{d}", 
                        callback_data=f"daysel:{mode}:{year}:{month}:{d}"
                    ))
        kb.append(row)
    
    kb.append([
        InlineKeyboardButton("◀️", callback_data=f"chmonth:{mode}:{year}:{month-1}"),
        InlineKeyboardButton("Сегодня 🟢", callback_data=f"chmonth:{mode}:today"),
        InlineKeyboardButton("▶️", callback_data=f"chmonth:{mode}:{year}:{month+1}")
    ])
    kb.append([InlineKeyboardButton("🔙 Назад", callback_data="menu")])
    return InlineKeyboardMarkup(kb)


def format_original_date(original_iso, today_iso):
    """Форматирует исходную дату для отображения"""
    if not original_iso or original_iso == today_iso:
        return ""
    
    try:
        orig_date = date.fromisoformat(original_iso)
        today_date = date.fromisoformat(today_iso)
        days_diff = (today_date - orig_date).days
        
        if days_diff == 0:
            return ""
        elif days_diff == 1:
            return " (вчера)"
        elif days_diff < 7:
            return f" ({days_diff} дн. назад)"
        else:
            return f" ({orig_date.strftime('%d.%m.%Y')})"
    except:
        return ""


def normalize_month(year, month):
    while month < 1: 
        year -= 1
        month += 12
    while month > 12: 
        year += 1
        month -= 12
    return year, month

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_profile_image()
    user = update.effective_user
    
    # Формируем имя пользователя
    user_name = user.first_name or ""
    if user.last_name:
        user_name = f"{user_name} {user.last_name}".strip()
    user_name = user_name or "друг"
    
    welcome_text = Messages.welcome(user_name)
    
    try:
        with open(Config.PROFILE_PNG, "rb") as f:
            await update.message.reply_photo(photo=InputFile(f), caption=welcome_text)
    except Exception:
        await update.message.reply_text(welcome_text)
    
    await update.message.reply_text(Messages.start_actions(), reply_markup=REPLY_KEYBOARD)

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != Config.ADMIN_ID:
        await update.message.reply_text("❌ Нет доступа.")
        return
    
    try:
        # Получаем статистику из базы данных
        with get_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT COUNT(*) FROM reminders")
            reminders_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM tasks")
            tasks_count = cur.fetchone()[0]
        
        message = (
            f"📊 Статистика бота:\n\n"
            f"⏰ Напоминаний: {reminders_count}\n"
            f"✅ Задач: {tasks_count}"
        )
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        await update.message.reply_text("❌ Ошибка при получении статистики.")

async def show_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список активных напоминаний пользователя"""
    user_id = update.effective_user.id
    now = user_now()
    
    try:
        with get_connection() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT title, scheduled_iso, lead_minutes 
                FROM reminders 
                WHERE user_id=? AND sent=0 AND scheduled_iso > ?
                ORDER BY scheduled_iso
            """, (user_id, now.isoformat()))
            rows = cur.fetchall()
    except Exception as e:
        logger.error(f"Database error in show_reminders: {e}")
        await update.message.reply_text("❌ Ошибка при получении напоминаний.")
        return

    if not rows:
        await update.message.reply_text(Messages.no_reminders(), reply_markup=REPLY_KEYBOARD)
        return

    reminders_list = []
    for title, scheduled_iso, lead_minutes in rows:
        # Преобразуем строку в datetime с часовым поясом
        scheduled_dt = datetime.fromisoformat(scheduled_iso).astimezone(ZoneInfo(Config.TZ))
        time_str = scheduled_dt.strftime('%d.%m.%Y %H:%M')
        reminders_list.append(Messages.reminder_item(title, time_str, lead_minutes))

    message = Messages.reminders_list_header() + "\n\n" + "\n".join(reminders_list)
    await update.message.reply_text(message, reply_markup=REPLY_KEYBOARD)

async def open_calendar_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        data = update.callback_query.data
    else:
        data = "open_calendar:create_reminder"
    
    try:
        _, mode = data.split(":")
    except Exception:
        mode = "view"
    
    now = user_now()
    markup = build_month_keyboard(now.year, now.month, mode=mode)
    text = "📅 Выберите день в календаре:"
    
    if update.callback_query:
        await safe_edit_message(update.callback_query.message, text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)

async def chmonth_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    data = update.callback_query.data
    parts = data.split(":")
    now = user_now()
    
    # Установим значения по умолчанию
    mode = "create_reminder"
    y = now.year
    m = now.month
    
    try:
        # Обработка разных форматов callback_data
        if len(parts) >= 4:
            if parts[2] == "today":
                # Формат: chmonth:mode:today
                mode = parts[1]
            else:
                # Формат: chmonth:mode:year:month
                mode = parts[1]
                y = int(parts[2])
                m = int(parts[3])
        elif len(parts) == 3 and parts[2] == "today":
            # Формат: chmonth:mode:today
            mode = parts[1]
        elif len(parts) == 3:
            # Формат: chmonth:year:month
            y = int(parts[1])
            m = int(parts[2])
        
        # Нормализуем месяц
        y, m = normalize_month(y, m)
        
    except Exception as e:
        logger.error(f"Error parsing chmonth callback: {e}")
        # В случае ошибки используем текущую дату
        y, m = now.year, now.month
    
    # Для режима просмотра задач разрешаем прошлые даты
    disable_past = mode != "view_tasks"
    markup = build_month_keyboard(y, m, mode=mode, disable_past=disable_past)
    await safe_edit_message(update.callback_query.message, text=None, reply_markup=markup)

async def day_selection_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    data = update.callback_query.data
    
    try:
        _, mode, year, month, day = data.split(":")
        year = int(year)
        month = int(month)
        day = int(day)
    except Exception:
        await update.callback_query.answer("❌ Ошибка в callback", show_alert=True)
        return
        
    selected_date = date(year, month, day)
    
    if mode == "create_reminder":
        context.user_data['new_reminder'] = {'year': year, 'month': month, 'day': day}
        await show_hours_page(update.callback_query.message)
        
    elif mode == "view_tasks":
        user_id = update.effective_user.id
        day_iso = selected_date.isoformat()
        
        try:
            with get_connection() as con:
                cur = con.cursor()
                cur.execute("""
                    SELECT description, status 
                    FROM tasks 
                    WHERE user_id=? AND day_iso=?
                    ORDER BY id
                """, (user_id, day_iso))
                rows = cur.fetchall()
        except Exception as e:
            logger.error(f"Database error: {e}")
            await update.callback_query.answer("❌ Ошибка базы данных", show_alert=True)
            return
        
        if not rows:
            txt = f"📅 Задачи за {day_iso}:\n\nНет задач на эту дату."
        else:
            completed = []
            pending = []
            for desc, status in rows:
                if status == "completed":
                    completed.append(f"✅ {desc}")
                else:
                    pending.append(f"❌ {desc}")
            
            txt = f"📅 Задачи за {day_iso}:\n"
            if completed:
                txt += "\n" + "\n".join(completed)
            if pending:
                txt += "\n" + "\n".join(pending)
        
        back_button = InlineKeyboardButton("🔙 Назад к календарю", callback_data="open_calendar:view_tasks")
        await safe_edit_message(
            update.callback_query.message, 
            txt, 
            reply_markup=InlineKeyboardMarkup([[back_button]])
        )
    else:
        await update.callback_query.answer("❌ Неподдерживаемый режим", show_alert=True)

async def show_hours_page(message):
    markup = build_hours_keyboard()
    await safe_edit_message(message, "⏰ Выберите час:", reply_markup=markup)

async def hoursel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    _, hh = update.callback_query.data.split(":")
    hh = int(hh)
    
    if 'new_reminder' not in context.user_data:
        context.user_data['new_reminder'] = {}
    
    context.user_data['new_reminder']['hour'] = hh
    
    kb = [
        [InlineKeyboardButton("00", callback_data="minutesel:0"),
         InlineKeyboardButton("15", callback_data="minutesel:15"),
         InlineKeyboardButton("30", callback_data="minutesel:30"),
         InlineKeyboardButton("45", callback_data="minutesel:45")],
        [InlineKeyboardButton("🔙 Назад", callback_data="open_calendar:create_reminder")]
    ]
    
    await safe_edit_message(
        update.callback_query.message, 
        f"⏱️ Выбран час: {hh:02d}\nВыберите минуты:", 
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def minute_select_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    _, mm = update.callback_query.data.split(":")
    mm = int(mm)
    
    if 'new_reminder' not in context.user_data:
        context.user_data['new_reminder'] = {}
    
    context.user_data['new_reminder']['minute'] = mm
    nr = context.user_data['new_reminder']
    
    y, m, d = nr['year'], nr['month'], nr['day']
    h, mi = nr['hour'], mm
    
    kb = [
        [InlineKeyboardButton("Отправлю напоминание за 0 мин", callback_data="lead:0"),
         InlineKeyboardButton("За 5 мин", callback_data="lead:5"),
         InlineKeyboardButton("За 10 мин", callback_data="lead:10")],
        [InlineKeyboardButton("За 30 мин", callback_data="lead:30"),
         InlineKeyboardButton("За 60 мин", callback_data="lead:60")],
        [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_reminder"),
         InlineKeyboardButton("❌ Отмена", callback_data="open_calendar:create_reminder")]
    ]
    
    await safe_edit_message(
        update.callback_query.message, 
        f"📅 Дата: {d}.{m}.{y}\n⏰ Время: {h:02d}:{mi:02d}\n\nВыберите когда напомнить:",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def lead_select_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    _, lm = update.callback_query.data.split(":")
    lm = int(lm)
    
    if 'new_reminder' not in context.user_data:
        context.user_data['new_reminder'] = {}
    
    context.user_data['new_reminder']['lead'] = lm
    await safe_edit_message(
        update.callback_query.message, 
        "✏️ Введите название события (отправьте текстом):", 
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="open_calendar:create_reminder")]])
    )
    context.user_data['awaiting_title'] = True

async def confirm_save_reminder_from_title(update: Update, context: ContextTypes.DEFAULT_TYPE, title_text: str):
    if 'new_reminder' not in context.user_data:
        await update.message.reply_text("❌ Нет данных напоминания. Начните заново.", reply_markup=REPLY_KEYBOARD)
        context.user_data.pop('awaiting_title', None)
        return
    
    nr = context.user_data['new_reminder']
    y, m, d = nr['year'], nr['month'], nr['day']
    h, mi = nr.get('hour', 0), nr.get('minute', 0)
    lead = nr.get('lead', 0)
    
    try:
        # Создаем datetime с часовым поясом
        scheduled_local = datetime(y, m, d, h, mi, tzinfo=ZoneInfo(Config.TZ))
    except Exception as e:
        logger.error(f"Invalid datetime: {e}")
        await update.message.reply_text("❌ Некорректная дата/время.", reply_markup=REPLY_KEYBOARD)
        return
    
    if scheduled_local <= user_now():
        await update.message.reply_text("❌ Нельзя создавать напоминание на прошлое время.", reply_markup=REPLY_KEYBOARD)
        context.user_data.pop('awaiting_title', None)
        return
    
    title = title_text.strip() or f"Событие {d}.{m}.{y} {h:02d}:{mi:02d}"
    created_iso = user_now().isoformat()
    
    try:
        # Используем соединение, чтобы получить ID созданной записи
        with get_connection() as con:
            cur = con.cursor()
            cur.execute(
                "INSERT INTO reminders (user_id, title, scheduled_iso, lead_minutes, created_iso) "
                "VALUES (?, ?, ?, ?, ?)",
                (update.effective_user.id, title, scheduled_local.isoformat(), lead, created_iso)
            )
            reminder_id = cur.lastrowid
            con.commit()
        
        # Получаем планировщик из контекста приложения
        scheduler_manager = context.application.scheduler_manager
        
        # Планируем напоминание с правильным ID
        await scheduler_manager.schedule_reminder(
            reminder_id,
            update.effective_user.id,
            title,
            scheduled_local,
            lead
        )
        
        time_str = scheduled_local.strftime('%d.%m.%Y %H:%M')
        await update.message.reply_text(
            Messages.reminder_created(title, time_str, lead),
            reply_markup=REPLY_KEYBOARD
        )
    except Exception as e:
        logger.error(f"Error saving reminder: {e}")
        await update.message.reply_text("❌ Ошибка при создании напоминания.", reply_markup=REPLY_KEYBOARD)
    
    context.user_data.pop('new_reminder', None)
    context.user_data.pop('awaiting_title', None)

async def confirm_reminder_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await safe_edit_message(
        update.callback_query.message, 
        "⚠️ Пожалуйста, сначала укажите название события.", 
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="open_calendar:create_reminder")]])
    )

async def today_tasks_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query: 
        await update.callback_query.answer()
    
    user_id = update.effective_user.id
    today_iso = user_now().date().isoformat()
    
    try:
        with get_connection() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT id, description, status, original_day_iso 
                FROM tasks 
                WHERE user_id=? AND day_iso=?
                ORDER BY 
                    CASE WHEN original_day_iso < ? THEN 0 ELSE 1 END,
                    original_day_iso ASC
            """, (user_id, today_iso, today_iso))
            rows = cur.fetchall()
    except Exception as e:
        logger.error(f"Database error: {e}")
        if update.callback_query:
            await update.callback_query.message.reply_text("❌ Ошибка базы данных")
        else:
            await update.message.reply_text("❌ Ошибка базы данных")
        return
    
    kb = []
    if not rows:
        txt = Messages.no_tasks()
    else:
        tasks_list = []
        for tid, desc, status, original_iso in rows:
            # Форматируем исходную дату
            date_str = format_original_date(original_iso, today_iso)
                    
            tasks_list.append(Messages.task_item(status == "completed", desc, date_str))
            
            # Добавляем кнопку для задачи
            kb.append([InlineKeyboardButton(
                f"{'✅ Выполнено' if status == 'completed' else '❌ Не выполнено'}: {desc[:20]}", 
                callback_data=f"toggle_task:{tid}"
            )])
        
        txt = Messages.task_list_header() + "\n" + "\n".join(tasks_list)
    
    kb.append([InlineKeyboardButton("➕ Добавить задачу", callback_data="add_task")])
    kb.append([InlineKeyboardButton("🔙 Назад", callback_data="menu")])
    
    if update.callback_query:
        await safe_edit_message(update.callback_query.message, txt, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))

async def toggle_task_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    _, tid = update.callback_query.data.split(":")
    tid = int(tid)
    
    try:
        with get_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT status, user_id FROM tasks WHERE id=?", (tid,))
            row = cur.fetchone()
            
            if not row:
                await safe_edit_message(
                    update.callback_query.message, 
                    "❌ Задача не найдена.", 
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="today_tasks")]])
                )
                return
            
            status, uid = row
            if uid != update.effective_user.id:
                await update.callback_query.answer("⚠️ Это не ваша задача.", show_alert=True)
                return
            
            if status == "pending":
                cur.execute(
                    "UPDATE tasks SET status='completed', completed_iso=? WHERE id=?",
                    (user_now().isoformat(), tid)
                )
                new_status = "✅ Выполнено"
            else:
                cur.execute(
                    "UPDATE tasks SET status='pending', completed_iso=NULL WHERE id=?",
                    (tid,)
                )
                new_status = "❌ Не выполнено"
            
            con.commit()
        
        await safe_edit_message(
            update.callback_query.message, 
            f"🔄 Статус задачи изменён на: {new_status}", 
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Обновить список", callback_data="today_tasks")],
                [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
            ])
        )
    except Exception as e:
        logger.error(f"Error toggling task: {e}")
        await update.callback_query.answer("❌ Ошибка при обновлении задачи", show_alert=True)

async def add_task_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data['adding_task'] = True
        await safe_edit_message(
            update.callback_query.message, 
            "✏️ Отправьте текст задачи:", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="today_tasks")]])
        )
    else:
        context.user_data['adding_task'] = True
        await update.message.reply_text("✏️ Отправьте текст задачи:")

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    
    # Обработка кнопок меню
    if text == "📅 Создать напоминание":
        await open_calendar_cb(update, context)
        return
    
    if text == "✅ Список дел на сегодня":
        await today_tasks_cb(update, context)
        return
    
    if text == "📊 Просмотреть задачи по дате":
        now = user_now()
        markup = build_month_keyboard(now.year, now.month, mode="view_tasks", disable_past=False)
        await update.message.reply_text("📅 Выберите дату для просмотра задач:", reply_markup=markup)
        return
    
    if text == "📋 Мои напоминания":
        await show_reminders(update, context)
        return
    
    if text == "ℹ️ О боте":
        await update.message.reply_text(Messages.bot_about(), reply_markup=REPLY_KEYBOARD)
        return
    
    # Ожидание названия события
    if context.user_data.get('awaiting_title'):
        await confirm_save_reminder_from_title(update, context, text)
        return
    
    # Добавление новой задачи
    if context.user_data.get('adding_task'):
        if not text:
            await update.message.reply_text("❌ Пустая задача не сохранена.")
            return
        
        try:
            today_iso = user_now().date().isoformat()
            execute_sql(
                "INSERT INTO tasks (user_id, description, day_iso, created_iso, original_day_iso) "
                "VALUES (:user_id, :description, :day_iso, :created_iso, :day_iso)",
                {
                    "user_id": update.effective_user.id,
                    "description": text,
                    "day_iso": today_iso,
                    "created_iso": user_now().isoformat()
                }
            )
            context.user_data.pop('adding_task', None)
            await update.message.reply_text("✅ Задача добавлена!", reply_markup=REPLY_KEYBOARD)
        except Exception as e:
            logger.error(f"Error adding task: {e}")
            await update.message.reply_text("❌ Ошибка при добавлении задачи", reply_markup=REPLY_KEYBOARD)
        return
    
    # Обработка неизвестных сообщений
    await update.message.reply_text("🤔 Используй меню рядом со строкой ввода или команду /start.", reply_markup=REPLY_KEYBOARD)

async def unknown_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()