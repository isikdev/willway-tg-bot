import os
from telegram import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
from telegram.ext import CallbackContext
from log import logger

def main():
    """Запуск бота."""
    logger.info("Запуск бота")
    
    # Создаем Updater и добавляем токен бота
    updater = Updater(os.getenv("BOT_TOKEN"), use_context=True)
    
    # Получаем диспетчер для регистрации обработчиков
    dp = updater.dispatcher
    
    # Регистрируем обработчик команды /start
    dp.add_handler(CommandHandler("start", start))
    
    # Регистрируем обработчик команды /help
    dp.add_handler(CommandHandler("help", help_command))
    
    # Регистрируем обработчик команды /reload_config
    dp.add_handler(CommandHandler("reload_config", reload_config))
    
    # Регистрируем обработчик текстовых сообщений
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text_messages))
    
    # Регистрируем обработчик для коллбэков от кнопок
    dp.add_handler(CallbackQueryHandler(handle_menu_callback, pattern='^(health|subscription|support|invite|menu)$'))
    
    # Регистрируем обработчик ошибок
    dp.add_error_handler(error_handler)
    
    # Получаем порт для webhook
    PORT = int(os.environ.get("PORT", "8443"))
    
    # Определяем, запускаем ли мы бота в режиме webhook или polling
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
    
    if WEBHOOK_URL:
        # Запускаем бота в режиме webhook
        updater.start_webhook(listen="0.0.0.0",
                             port=PORT,
                             url_path=os.getenv("BOT_TOKEN"),
                             webhook_url=WEBHOOK_URL + os.getenv("BOT_TOKEN"))
        logger.info(f"Бот запущен в режиме webhook на порту {PORT}")
    else:
        # Запускаем бота в режиме polling
        updater.start_polling()
        logger.info("Бот запущен в режиме polling")
    
    # Запускаем бота до получения сигнала на остановку
    updater.idle() 