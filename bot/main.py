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
    reload_config, get_bot_config, apply_bot_config, bot_info, invite_friend, handle_copy_ref_link,
    GENDER, AGE, HEIGHT, WEIGHT, MAIN_GOAL, ADDITIONAL_GOAL,
    WORK_FORMAT, SPORT_FREQUENCY, PAYMENT, SUPPORT_OPTIONS, show_referral_stats, start_survey
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
    """Обрабатывает реферальную ссылку блогера"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    args = context.args
    
    logger.info(f"[REFERRAL] Обнаружен реферальный код: {args[0] if args else 'None'}")
    
    # Обрабатываем ссылки как с префиксом ref_, так и без него
    if args and (args[0].startswith('ref_') or len(args[0]) >= 10):  # Проверяем минимальную длину ключа
        try:
            # Получаем код как с префиксом, так и без
            original_code = args[0]
            clean_code = args[0].replace('ref_', '')  # Код без префикса
            
            logger.info(f"[REFERRAL] Обработка реферального кода блогера. Оригинальный код: {original_code}, очищенный код: {clean_code}")
            
            # Вызываем track_referral_click напрямую с оригинальным кодом
            # Функция track_referral_click уже умеет обрабатывать оба варианта ключа
            success, result = track_referral_click(original_code, user_id, username)
            
            if success:
                logger.info(f"Успешно зарегистрирован клик по реферальной ссылке блогера: {result}")
                # Сохраняем реферальный код в контексте пользователя
                user_data = context.user_data
                user_data['blogger_ref_code'] = clean_code  # Всегда сохраняем очищенный код
                
                # Сохраняем реферальный код в базе данных пользователя
                try:
                    session = get_session()
                    user = session.query(User).filter(User.user_id == user_id).first()
                    
                    if user:
                        user.blogger_ref_code = clean_code  # Всегда сохраняем очищенный код
                        user.referral_source = 'blogger'
                        session.commit()
                        logger.info(f"Реферальный код блогера {clean_code} сохранен в базе для пользователя {user_id}")
                    else:
                        # Создаем пользователя с реферальным кодом
                        new_user = User(
                            user_id=user_id,
                            username=username,
                            blogger_ref_code=clean_code,  # Всегда сохраняем очищенный код
                            referral_source='blogger',
                            registration_date=datetime.now(),
                            first_interaction_time=datetime.now()
                        )
                        session.add(new_user)
                        session.commit()
                        logger.info(f"Создан новый пользователь {user_id} с реферальным кодом блогера {clean_code}")
                    
                    session.close()
                except Exception as db_error:
                    logger.error(f"Ошибка при сохранении реферального кода в базе: {str(db_error)}")
                    import traceback
                    logger.error(f"Трассировка: {traceback.format_exc()}")
                
                return True
            else:
                logger.error(f"Ошибка при регистрации клика по реферальной ссылке: {result}")
        except Exception as e:
            logger.error(f"Ошибка при обработке реферальной ссылки блогера: {str(e)}")
            import traceback
            logger.error(f"Трассировка: {traceback.format_exc()}")
    
    return False

# Переопределяем функцию start из импортированного модуля
def start_wrapper(update: Update, context: CallbackContext) -> int:
    """Обертка для функции start с обработкой реферальных ссылок блогеров"""
    user_id = update.effective_user.id
    args = context.args
    referral_code = args[0] if args else None
    
    # Проверяем ссылки как с префиксом ref_, так и без него
    # Если длина кода > 10 символов, считаем, что это может быть код блогера
    if referral_code and (referral_code.startswith('ref_') or len(referral_code) >= 10):
        # Проверяем и обрабатываем реферальную ссылку блогера
        blogger_ref_processed = process_blogger_referral(update, context)
        
        # Если реферальный код блогера обработан успешно, отправляем приветственное сообщение
        # и прерываем стандартную обработку рефералов
        if blogger_ref_processed and 'blogger_ref_code' in context.user_data:
            blogger_code = context.user_data['blogger_ref_code']
            
            try:
                session = get_session()
                user = session.query(User).filter(User.user_id == user_id).first()
                
                # Если пользователь не существует, создаем его
                if not user:
                    user = User(
                        user_id=user_id,
                        username=update.effective_user.username,
                        registration_date=datetime.now(),
                        first_interaction_time=datetime.now(),
                        registered=False,
                        blogger_ref_code=blogger_code,
                        referral_source='blogger'
                    )
                    session.add(user)
                else:
                    # Иначе обновляем существующего пользователя
                    user.blogger_ref_code = blogger_code
                    user.referral_source = 'blogger'
                
                session.commit()
                logger.info(f"[BLOGGER_REFERRAL] Сохранен код блогера {blogger_code} для пользователя {user_id}")
                
                # Отправляем приветственное видео
                from bot.handlers import send_welcome_video
                send_welcome_video(update, context)
                
                # Отправляем сообщение о главном меню
                from bot.handlers import get_main_keyboard, menu_keyboard
                update.message.reply_text(
                    "Добро пожаловать! Выберите действие из меню:",
                    reply_markup=get_main_keyboard()
                )
                
                update.message.reply_text(
                    "Главное меню:",
                    reply_markup=InlineKeyboardMarkup(menu_keyboard())
                )
                
                session.close()
                return ConversationHandler.END
                
            except Exception as e:
                logger.error(f"[BLOGGER_REFERRAL] Ошибка при сохранении кода блогера: {str(e)}")
                import traceback
                logger.error(f"Трассировка: {traceback.format_exc()}")
    
    # Если это не код блогера или обработка не удалась, вызываем оригинальную функцию start
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
    
    # Добавляем обработчик для реферальной программы
    dispatcher.add_handler(CallbackQueryHandler(invite_friend, pattern='^invite_friend$'))
    dispatcher.add_handler(MessageHandler(Filters.regex('^Пригласить друга$'), invite_friend))
    dispatcher.add_handler(CallbackQueryHandler(show_referral_stats, pattern='^show_referral_stats$'))
    
    # Добавляем обработчик копирования реферальной ссылки (упрощенная версия)
    dispatcher.add_handler(CallbackQueryHandler(handle_copy_ref_link, pattern='^copy_ref_link_'))
    
    # Регистрация обработчиков кнопок меню
    # Обработчик кнопки "Назад" должен иметь высокий приоритет
    dispatcher.add_handler(MessageHandler(
        Filters.regex('^Назад$'), 
        back_to_main_menu
    ), group=0)  # Более низкий номер группы = более высокий приоритет
    
    dispatcher.add_handler(MessageHandler(
        Filters.regex('^Health ассистент$'), 
        health_assistant_button
    ), group=1)
    
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
    ), group=2)
    
    # Все остальные текстовые сообщения идут в Health ассистент
    dispatcher.add_handler(MessageHandler(
        Filters.text & ~Filters.command & ~menu_filter & ~Filters.regex('^Назад$') & ~Filters.regex('^Health ассистент$'),
        handle_health_assistant_message
    ), group=3)
    
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
