import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from config import Config
from database import get_connection

logger = logging.getLogger(__name__)

class SchedulerManager:
    def __init__(self, app):
        self.app = app
        self.scheduler = AsyncIOScheduler(timezone=ZoneInfo(Config.TZ))
        logger.info("Scheduler initialized")
        self.active_jobs = {}
        
    async def start_scheduler(self):
        """Запускает планировщик"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")

    async def schedule_reminder(self, reminder_id, user_id, title, scheduled_dt_local, lead_minutes):
        # Рассчитываем время отправки напоминания
        send_at = scheduled_dt_local - timedelta(minutes=lead_minutes)
        now = datetime.now(ZoneInfo(Config.TZ))
        
        # Проверяем, не прошло ли уже время
        if send_at <= now:
            logger.warning(f"Send time in past, skipping schedule: {send_at} <= {now}")
            
            # Помечаем напоминание как отправленное, если время уже прошло
            try:
                with get_connection() as con:
                    con.execute(
                        "UPDATE reminders SET sent=1 WHERE id=?",
                        (reminder_id,)
                    )
                    con.commit()
                logger.info(f"Marked past reminder {reminder_id} as sent")
            except Exception as e:
                logger.error(f"Failed to mark past reminder as sent: {e}")
                
            return False
        
        job_id = f"reminder_{reminder_id}"
        
        # Удаляем старую задачу, если существует
        if job_id in self.active_jobs:
            try:
                self.scheduler.remove_job(job_id)
                logger.debug(f"Removed existing job: {job_id}")
            except Exception as e:
                logger.error(f"Error removing job {job_id}: {e}")
        
        # Создаем задачу для отправки напоминания
        async def send_reminder_task():
            try:
                logger.info(f"Executing reminder job: {job_id}")
                
                # Форматируем время для пользователя
                time_str = scheduled_dt_local.strftime('%d.%m.%Y %H:%M')
                message = (
                    f"🔔 Напоминание: {title}\n"
                    f"⏰ Время события: {time_str}"
                )
                
                if lead_minutes > 0:
                    message += f"\nОтправлено за {lead_minutes} мин. до события"
                
                await self.app.bot.send_message(chat_id=user_id, text=message)
                logger.info(f"Reminder sent to user {user_id}")
                
                # Отмечаем напоминание как отправленное в БД
                with get_connection() as con:
                    con.execute(
                        "UPDATE reminders SET sent=1 WHERE id=?",
                        (reminder_id,)
                    )
                    con.commit()
                logger.info(f"Reminder {reminder_id} marked as sent")
                
            except Exception as e:
                logger.error(f"Failed to send reminder {job_id}: {e}", exc_info=True)
            finally:
                # Удаляем задачу из активных
                if job_id in self.active_jobs:
                    del self.active_jobs[job_id]

        try:
            # Создаем и запускаем фоновую задачу
            job = self.scheduler.add_job(
                send_reminder_task,  # Передаем корутину напрямую
                trigger=DateTrigger(run_date=send_at),
                id=job_id
            )
            
            self.active_jobs[job_id] = job
            logger.info(f"Scheduled reminder {job_id} for {send_at.isoformat()}")
            return True
        except Exception as e:
            logger.error(f"Failed to schedule job {job_id}: {e}", exc_info=True)
            return False

    async def schedule_existing_reminders(self):
        logger.info("Scheduling existing reminders")
        try:
            with get_connection() as con:
                cur = con.cursor()
                cur.execute(
                    "SELECT id, user_id, title, scheduled_iso, lead_minutes "
                    "FROM reminders WHERE sent=0"
                )
                rows = cur.fetchall()
            
            now = datetime.now(ZoneInfo(Config.TZ))
            for row in rows:
                rem_id, user_id, title, sched_iso, lead = row
                try:
                    # Преобразуем строку в datetime с часовым поясом
                    scheduled_dt = datetime.fromisoformat(sched_iso).replace(tzinfo=ZoneInfo(Config.TZ))
                    
                    # Проверяем, не прошло ли уже время события
                    if scheduled_dt <= now:
                        # Помечаем напоминание как отправленное, если время уже прошло
                        with get_connection() as con:
                            con.execute(
                                "UPDATE reminders SET sent=1 WHERE id=?",
                                (rem_id,)
                            )
                            con.commit()
                        logger.info(f"Marked past reminder {rem_id} as sent")
                        continue
                        
                    await self.schedule_reminder(rem_id, user_id, title, scheduled_dt, lead)
                except Exception as e:
                    logger.error(f"Failed to schedule existing reminder {rem_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error scheduling existing reminders: {e}", exc_info=True)

    def rollover_pending_tasks(self):
        logger.info("Running daily rollover")
        try:
            today = datetime.now(ZoneInfo(Config.TZ)).date()
            tomorrow = today + timedelta(days=1)
            
            # Обновляем только задачи без исходной даты
            with get_connection() as con:
                # Для задач, у которых original_day_iso не установлен (старые задачи) устанавливаем original_day_iso = day_iso
                con.execute(
                    "UPDATE tasks SET original_day_iso = day_iso WHERE original_day_iso = '' AND status='pending'"
                )
                con.commit()

                # Теперь обновляем day_iso на завтра для всех невыполненных задач на сегодня
                con.execute(
                    "UPDATE tasks SET day_iso=? WHERE day_iso=? AND status='pending'",
                    (tomorrow.isoformat(), today.isoformat())
                )
                con.commit()
            
            logger.info(f"Rolled over tasks from {today} to {tomorrow}")
        except Exception as e:
            logger.error(f"Error in task rollover: {e}", exc_info=True)

    def rollover_all_pending_tasks(self):
        """Переносит все невыполненные задачи на следующий день"""
        logger.info("Running complete task rollover")
        try:
            today = datetime.now(ZoneInfo(Config.TZ)).date()
            tomorrow = today + timedelta(days=1)
            
            with get_connection() as con:
                # Устанавливаем original_day_iso для задач, у которых его нет
                con.execute(
                    "UPDATE tasks SET original_day_iso = day_iso WHERE original_day_iso = '' AND status='pending'"
                )
                con.commit()
                
                # Переносим все невыполненные задачи на сегодняшний день на завтра
                con.execute(
                    "UPDATE tasks SET day_iso=? WHERE day_iso<=? AND status='pending'",
                    (tomorrow.isoformat(), today.isoformat())
                )
                con.commit()
            
            logger.info(f"Rolled over all pending tasks to {tomorrow}")
        except Exception as e:
            logger.error(f"Error in complete task rollover: {e}", exc_info=True)