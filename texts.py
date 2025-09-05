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
    def task_item(completed: bool, description: str, original_date: str = "") -> str:
        emoji = "✅" if completed else "❌"
        date_info = f" ({original_date})" if original_date else ""
        return f"{emoji} {description}{date_info}"
    
    # Технические сообщения
    @staticmethod
    def maintenance_notification() -> str:
        return (
            "⚠️🚧 Внимание! Бот временно не работает, ведутся технические работы. "
            "Мы скоро вернемся с улучшениями! 🛠️⏳ Приносим извинения за неудобства."
        )
    
    # ... другие тексты ...