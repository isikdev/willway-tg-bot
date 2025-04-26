import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Updater, Dispatcher, CallbackContext, ConversationHandler, CommandHandler,
    MessageHandler, Filters, CallbackQueryHandler
)
from dotenv import load_dotenv
import sys
from datetime import datetime, timedelta
from pyairtable import Api
from .gpt_assistant import get_health_assistant_response
import re

# Добавляем путь к корневой директории проекта
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.models import init_db, User, get_session
from bot.handlers import (
    start, gender, age, height, weight, main_goal, additional_goal,
    work_format, sport_frequency, payment, handle_menu_callback, cancel, clear,
    handle_text_messages, health_assistant_button, handle_health_assistant_message, back_to_main_menu,
    reload_config, get_bot_config, apply_bot_config, bot_info,
    GENDER, AGE, HEIGHT, WEIGHT, MAIN_GOAL, ADDITIONAL_GOAL,
    WORK_FORMAT, SPORT_FREQUENCY, PAYMENT, SUPPORT_OPTIONS
)

# Добавляем импорт для реферальных ссылок блогеров
from api_patch import track_referral_click

# Система платежей отключена

load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def process_blogger_referral(update: Update, context: CallbackContext) -> bool:
    """Обработка реферальной ссылки блогера"""
    user_id = update.effective_user.id
    message_text = update.message.text if update.message else None
    
    if message_text and message_text.startswith('/start ref_'):
        try:
            # Извлекаем реферальный код
            ref_code = message_text.replace('/start ', '')
            
            # Проверяем соответствие формату реферального кода блогера
            if ref_code.startswith('ref_'):
                logger.info(f"Пользователь {user_id} перешел по реферальной ссылке блогера: {ref_code}")
                
                # Регистрируем клик по реферальной ссылке
                username = update.effective_user.username or f"user_{user_id}"
                success, result = track_referral_click(ref_code, user_id, username)
                
                if success:
                    logger.info(f"Успешно зарегистрирован клик по реферальной ссылке блогера: {result}")
                    # Сохраняем реферальный код в контексте пользователя
                    user_data = context.user_data
                    user_data['blogger_ref_code'] = ref_code
                    
                    return True
                else:
                    logger.error(f"Ошибка при регистрации клика по реферальной ссылке: {result}")
        except Exception as e:
            logger.error(f"Ошибка при обработке реферальной ссылки блогера: {str(e)}")
    
    return False

# Переопределяем функцию start из импортированного модуля
def start_wrapper(update: Update, context: CallbackContext) -> int:
    """Обертка для функции start с обработкой реферальных ссылок блогеров"""
    # Проверяем и обрабатываем реферальную ссылку блогера
    process_blogger_referral(update, context)
    
    # Вызываем оригинальную функцию start
    return start(update, context)

def main():
    """Запуск бота."""
    # Инициализация базы данных
    init_db()
    
    # Получение токена бота из переменных окружения
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("Не задан BOT_TOKEN в переменных окружения!")
        exit(1)
    
    # Создание и настройка Updater
    updater = Updater(token)
    dispatcher = updater.dispatcher
    
    # Создание обработчика диалога для регистрации и сбора данных
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_wrapper),  # Используем нашу обертку вместо прямого вызова start
            CommandHandler("survey", start_survey),
            MessageHandler(Filters.regex(r'^Подобрать персональную программу$'), start_survey),
            CallbackQueryHandler(start_survey, pattern='^start_survey$')
        ],
        states={
            GENDER: [CallbackQueryHandler(gender, pattern='^(male|female)$')],
            AGE: [MessageHandler(Filters.text & ~Filters.command, age)],
            HEIGHT: [MessageHandler(Filters.text & ~Filters.command, height)],
            WEIGHT: [MessageHandler(Filters.text & ~Filters.command, weight)],
            MAIN_GOAL: [CallbackQueryHandler(main_goal)],
            ADDITIONAL_GOAL: [CallbackQueryHandler(additional_goal)],
            WORK_FORMAT: [CallbackQueryHandler(work_format)],
            SPORT_FREQUENCY: [CallbackQueryHandler(sport_frequency)],
            PAYMENT: [CallbackQueryHandler(payment)],
            SUPPORT_OPTIONS: [CallbackQueryHandler(handle_menu_callback)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=True,
        name="survey_conversation"
    )
    
    # Добавление обработчиков
    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(CallbackQueryHandler(handle_menu_callback))
    
    # Регистрация обработчиков кнопок меню
    dispatcher.add_handler(MessageHandler(
        Filters.regex('^Health ассистент$'), 
        health_assistant_button
    ))
    
    dispatcher.add_handler(MessageHandler(
        Filters.regex('^Назад$'), 
        back_to_main_menu
    ))
    
    # Добавляем обработчик текстовых сообщений от кнопок меню и Health ассистента
    # Сначала проверяем наличие кнопок меню
    menu_filter = (
        Filters.regex('^Управление подпиской$') | 
        Filters.regex('^Связь с поддержкой$') |
        Filters.regex('^Пригласить друга$') |
        Filters.regex('^Меню ✅$') |
        Filters.regex('^😊 Анекдот$')
    )
    
    dispatcher.add_handler(MessageHandler(
        menu_filter & ~Filters.command, 
        handle_text_messages
    ))
    
    # Все остальные текстовые сообщения идут в Health ассистент
    dispatcher.add_handler(MessageHandler(
        Filters.text & ~Filters.command & ~menu_filter & ~Filters.regex('^Назад$') & ~Filters.regex('^Health ассистент$'),
        handle_health_assistant_message
    ))
    
    # Добавляем команду /clear для отладки
    dispatcher.add_handler(CommandHandler("clear", clear))
    
    # Добавляем команду /reload_config для обновления конфигурации
    dispatcher.add_handler(CommandHandler("reload_config", reload_config))
    logger.info("Зарегистрирована команда /reload_config")
    
    # Добавляем команды для информации о боте
    dispatcher.add_handler(CommandHandler("info", bot_info))
    dispatcher.add_handler(CommandHandler("about", bot_info))
    logger.info("Зарегистрированы команды /info и /about")
    
    # Система платежей отключена
    logger.info("Система платежей отключена")
    
    # Применяем конфигурацию при запуске бота
    try:
        logger.info("Применение начальной конфигурации...")
        config = get_bot_config()
        applied_settings = apply_bot_config(updater.bot, config)
        logger.info(f"Начальная конфигурация применена: {applied_settings}")
    except Exception as e:
        logger.error(f"Ошибка при применении начальной конфигурации: {e}")
    
    # Запуск бота
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
