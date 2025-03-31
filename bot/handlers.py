from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, Message
from telegram.ext import ContextTypes, ConversationHandler, Dispatcher, Updater, MessageHandler, Filters, CallbackQueryHandler, CommandHandler, CallbackContext
from datetime import datetime, timedelta
import sys
import os
import logging
from dotenv import load_dotenv
import asyncio
from pyairtable import Api
from .gpt_assistant import get_health_assistant_response
import json
import requests

# Добавляем путь к корневой директории проекта
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.models import User, get_session, AdminUser

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Импортируем адаптер для CloudPayments
try:
    from payment.payment_adapter import payment_adapter
    logger.info("CloudPayments адаптер успешно импортирован")
except ImportError as e:
    payment_adapter = None
    logger.error(f"Ошибка импорта CloudPayments адаптера: {e}")
    
load_dotenv()

# Создаем диспетчер и загружаем токен
TOKEN = os.getenv('BOT_TOKEN')
updater = Updater(TOKEN)
dp = updater.dispatcher

# Константы для конечного автомата (FSM)
(
    GENDER, 
    AGE, 
    HEIGHT, 
    WEIGHT, 
    MAIN_GOAL, 
    ADDITIONAL_GOAL, 
    WORK_FORMAT, 
    SPORT_FREQUENCY, 
    EMAIL,       # Новый этап для ввода email
    PHONE,       # Новый этап для ввода телефона
    PASSWORD,    # Новый этап для создания пароля
    PAYMENT, 
    MAIN,  # Новое состояние для главного меню
    GPT_ASSISTANT,
    SUBSCRIPTION,
    SUPPORT,
    INVITE,
    MENU
) = range(18)

# Airtable API настройки
AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
AIRTABLE_TABLE_ID = os.getenv('AIRTABLE_TABLE_ID')  # tblPToboz6SIWCzNU

# Инициализация Airtable API (если переменные окружения установлены)
airtable = None
table = None
use_direct_requests = True  # Флаг для использования прямых запросов

if AIRTABLE_API_KEY and AIRTABLE_BASE_ID and AIRTABLE_TABLE_ID:
    try:
        if not use_direct_requests:
            # Старый способ через pyairtable
            airtable = Api(AIRTABLE_API_KEY)
            table = airtable.table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID)
        logger.info("Airtable API настройки успешно загружены")
    except Exception as e:
        logger.error(f"Ошибка при инициализации Airtable API: {e}")
else:
    logger.warning("Переменные окружения для Airtable не установлены, функциональность Airtable отключена")

# Путь к файлу конфигурации бота
BOT_CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bot_config.json')

# Функция для проверки и исправления путей в конфигурации
def fix_image_paths(config):
    """Проверяет и исправляет пути к изображениям в конфигурации"""
    modified = False
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Проверяем путь к аватару бота
    if config.get('botpic_url'):
        botpic_rel_path = config.get('botpic_url').lstrip('/')
        botpic_abs_path = os.path.join(app_dir, 'web_admin', botpic_rel_path)
        
        if not os.path.exists(botpic_abs_path):
            logger.warning(f"Файл аватара бота не найден по пути: {botpic_abs_path}")
            
            # Проверяем альтернативные пути
            alt_paths = [
                os.path.join(app_dir, botpic_rel_path),
                os.path.join(app_dir, 'static', 'img', os.path.basename(botpic_rel_path)),
                os.path.join(app_dir, 'web_admin', 'static', 'img', os.path.basename(botpic_rel_path))
            ]
            
            for alt_path in alt_paths:
                if os.path.exists(alt_path):
                    logger.info(f"Найден файл аватара по альтернативному пути: {alt_path}")
                    # Вычисляем относительный путь от корня приложения
                    rel_path = os.path.relpath(alt_path, app_dir)
                    # Преобразуем в формат URL
                    url_path = rel_path.replace('\\', '/')
                    config['botpic_url'] = f"/{url_path}"
                    logger.info(f"Исправлен путь к аватару бота: {config['botpic_url']}")
                    modified = True
                    break
    
    # Проверяем путь к изображению описания
    if config.get('description_pic_url'):
        desc_pic_rel_path = config.get('description_pic_url').lstrip('/')
        desc_pic_abs_path = os.path.join(app_dir, 'web_admin', desc_pic_rel_path)
        
        if not os.path.exists(desc_pic_abs_path):
            logger.warning(f"Файл изображения описания не найден по пути: {desc_pic_abs_path}")
            
            # Проверяем альтернативные пути
            alt_paths = [
                os.path.join(app_dir, desc_pic_rel_path),
                os.path.join(app_dir, 'static', 'img', os.path.basename(desc_pic_rel_path)),
                os.path.join(app_dir, 'web_admin', 'static', 'img', os.path.basename(desc_pic_rel_path))
            ]
            
            for alt_path in alt_paths:
                if os.path.exists(alt_path):
                    logger.info(f"Найден файл изображения описания по альтернативному пути: {alt_path}")
                    # Вычисляем относительный путь от корня приложения
                    rel_path = os.path.relpath(alt_path, app_dir)
                    # Преобразуем в формат URL
                    url_path = rel_path.replace('\\', '/')
                    config['description_pic_url'] = f"/{url_path}"
                    logger.info(f"Исправлен путь к изображению описания: {config['description_pic_url']}")
                    modified = True
                    break
    
    # Если были внесены изменения, сохраняем конфигурацию
    if modified:
        try:
            with open(BOT_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            logger.info("Конфигурация с исправленными путями сохранена")
        except Exception as e:
            logger.error(f"Ошибка при сохранении конфигурации: {e}")
    
    return config

# Получение настроек бота из конфигурационного файла
def get_bot_config():
    """Получает конфигурацию бота из файла"""
    logger.info("Попытка чтения конфигурации бота")
    # Путь к файлу конфигурации (относительно корневой директории проекта)
    BOT_CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bot_config.json')
    
    logger.info(f"Путь к файлу конфигурации: {BOT_CONFIG_FILE}")
    logger.info(f"Файл существует: {os.path.exists(BOT_CONFIG_FILE)}")
    
    config = {
        "trainer_username": "telegram",
        "manager_username": "telegram"
    }
    
    try:
        with open(BOT_CONFIG_FILE, 'r', encoding='utf-8') as f:
            loaded_config = json.load(f)
            config.update(loaded_config)
            logger.info(f"Конфигурация загружена: {config.keys()}")
            
            # Проверка и обработка путей изображений
            if 'description_pic_url' in config and config['description_pic_url']:
                path = config['description_pic_url']
                logger.info(f"Найден путь изображения описания: {path}")
                
                # Преобразуем относительный путь в абсолютный
                if path.startswith('/'):
                    # Если путь начинается с /, убираем его
                    path = path[1:]
                
                # Преобразуем в абсолютный путь
                abs_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
                logger.info(f"Абсолютный путь изображения описания: {abs_path}")
                
                # Проверяем существование файла
                if os.path.exists(abs_path):
                    logger.info("Файл изображения описания существует")
                    config['description_pic_absolute_path'] = abs_path
                else:
                    logger.warning(f"Файл изображения описания не существует: {abs_path}")
            
            if 'botpic_url' in config and config['botpic_url']:
                path = config['botpic_url']
                logger.info(f"Найден путь изображения бота: {path}")
                
                # Преобразуем относительный путь в абсолютный
                if path.startswith('/'):
                    # Если путь начинается с /, убираем его
                    path = path[1:]
                
                # Преобразуем в абсолютный путь
                abs_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
                logger.info(f"Абсолютный путь изображения бота: {abs_path}")
                
                # Проверяем существование файла
                if os.path.exists(abs_path):
                    logger.info("Файл изображения бота существует")
                    config['botpic_absolute_path'] = abs_path
                else:
                    logger.warning(f"Файл изображения бота не существует: {abs_path}")
                
    except Exception as e:
        logger.error(f"Ошибка при чтении конфигурации бота: {e}")
    
    return config

# Применение конфигурации бота
def apply_bot_config(bot, config):
    """Применяет настройки из конфигурации к боту"""
    logger.info("Применение настроек бота...")
    
    # Словарь для отслеживания примененных настроек
    applied_settings = {
        "support_keyboard": False,
        "commands": False,
        "bot_name": False,
        "about_text": False,
        "description": False,
        "privacy_mode": False,
        "description_pic": False,
        "botpic": False
    }
    
    try:
        # Настройка команд бота через API Telegram
        if 'commands' in config and isinstance(config['commands'], dict):
            bot_commands = []
            for cmd, desc in config.get('commands', {}).items():
                # Убираем символ "/" если он есть в начале команды
                cmd_name = cmd[1:] if cmd.startswith('/') else cmd
                bot_commands.append((cmd_name, desc))
            
            if bot_commands:
                try:
                    # В зависимости от версии библиотеки можно использовать разные методы
                    # Для python-telegram-bot 13.x
                    bot.set_my_commands(bot_commands)
                    applied_settings["commands"] = True
                    logger.info(f"Обновлены команды бота: {bot_commands}")
                except Exception as e:
                    logger.error(f"Ошибка при обновлении команд бота: {e}")
        
        # Обновление имени и описания бота через BotFather требует отдельного API
        # Это нельзя сделать автоматически через python-telegram-bot
        # Вместо этого, мы можем вывести сообщение для администратора с инструкциями
        
        # В будущих версиях можно добавить автоматическое обновление через прямой API Telegram
        # Например, используя requests для отправки запросов к API:
        # response = requests.post(f"https://api.telegram.org/bot{TOKEN}/setMyName", 
        #    data={"name": config.get('bot_name')})
        
        # Для настроек, которые можно применить на лету в коде
        if 'privacy_mode' in config:
            # Например, можно хранить в боте настройку, которая влияет на обработку сообщений
            # бот будет использовать это значение для определения режима приватности
            applied_settings["privacy_mode"] = True
            logger.info(f"Обновлен режим приватности: {config.get('privacy_mode')}")
        
        # Если настройки имени, описания и т.д. можно как-то применить к боту,
        # то код для этого можно добавить здесь
        
        return applied_settings
        
    except Exception as e:
        logger.error(f"Ошибка при применении конфигурации к боту: {e}")
        return applied_settings

# Клавиатура для нижней части экрана
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("Health ассистент"), KeyboardButton("Управление подпиской")],
        [KeyboardButton("Связь с поддержкой"), KeyboardButton("Пригласить друга")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Клавиатуры для различных шагов
def gender_keyboard():
    keyboard = [
        [InlineKeyboardButton("Мужской", callback_data="м"),
         InlineKeyboardButton("Женский", callback_data="ж")]
    ]
    return InlineKeyboardMarkup(keyboard)

def main_goal_keyboard():
    keyboard = [
        [InlineKeyboardButton("✅ Снижение веса", callback_data="goal_1")],
        [InlineKeyboardButton("✅ Набор мышечной массы", callback_data="goal_2")],
        [InlineKeyboardButton("✅ Коррекция осанки", callback_data="goal_3")],
        [InlineKeyboardButton("✅ Убрать дряхлость в теле", callback_data="goal_4")],
        [InlineKeyboardButton("✅ Общий тонус/рельеф мышц", callback_data="goal_5")],
        [InlineKeyboardButton("✅ Восстановиться после родов", callback_data="goal_6")],
        [InlineKeyboardButton("✅ Снять эмоциональное напряжение", callback_data="goal_7")],
        [InlineKeyboardButton("✅ Улучшить качество сна", callback_data="goal_8")],
        [InlineKeyboardButton("✅ Стать более энергичным", callback_data="goal_9")],
        [InlineKeyboardButton("Готово ✓", callback_data="goals_done")]
    ]
    return InlineKeyboardMarkup(keyboard)

def additional_goal_keyboard():
    keyboard = [
        [InlineKeyboardButton("Узнать больше информации как заботиться о своем теле и здоровье", callback_data="Узнать больше информации")],
        [InlineKeyboardButton("Больше узнать о здоровом питании", callback_data="Здоровое питание")],
        [InlineKeyboardButton("Разобраться в себе с помощью психологии, медитаций, телесных практик", callback_data="Разобраться в себе")],
        [InlineKeyboardButton("Обрести новые знакомства", callback_data="Обрести новые знакомства")],
        [InlineKeyboardButton("Получить поддержку, обратную связь и мотивацию", callback_data="Получить поддержку")],
        [InlineKeyboardButton("Нет дополнительной цели", callback_data="Нет дополнительной цели")]
    ]
    return InlineKeyboardMarkup(keyboard)

def work_format_keyboard():
    keyboard = [
        [InlineKeyboardButton("Много сижу за компьютером, работаю в офисе/удаленно", callback_data="Сидячая работа")],
        [InlineKeyboardButton("Мама в декрете", callback_data="Мама в декрете")],
        [InlineKeyboardButton("Не работаю (на распродаже, на чиле)", callback_data="Не работаю")],
        [InlineKeyboardButton("Работа разъездного характера/частые командировки", callback_data="Разъездная работа")],
        [InlineKeyboardButton("Работа физического характера", callback_data="Физическая работа")]
    ]
    return InlineKeyboardMarkup(keyboard)

def sport_frequency_keyboard():
    keyboard = [
        [InlineKeyboardButton("1-2 раза в неделю", callback_data="1-2 раза в неделю")],
        [InlineKeyboardButton("3-4 раза в неделю", callback_data="3-4 раза в неделю")],
        [InlineKeyboardButton("5-6 раз в неделю", callback_data="5-6 раз в неделю")],
        [InlineKeyboardButton("Каждый день", callback_data="Каждый день")],
        [InlineKeyboardButton("Не занимаюсь", callback_data="Не занимаюсь")]
    ]
    return InlineKeyboardMarkup(keyboard)

def payment_keyboard():
    keyboard = [
        [InlineKeyboardButton("Подписка на месяц - 1,890р", callback_data="monthly")],
        [InlineKeyboardButton("Подписка на год - 17,777р (экономия 22%)", callback_data="yearly")],
        [InlineKeyboardButton("Посмотреть отзывы/кейсы", url="https://t.me/willway_reviews")]
    ]
    return InlineKeyboardMarkup(keyboard)

def menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("Health ассистент", callback_data="health_assistant")],
        [InlineKeyboardButton("Управление подпиской", callback_data="subscription_management")],
        [InlineKeyboardButton("Связь с поддержкой", callback_data="support")],
        [InlineKeyboardButton("Пригласить друга", callback_data="invite_friend")]
    ]
    return InlineKeyboardMarkup(keyboard)

def support_keyboard():
    # Каждый раз читаем конфигурацию заново
    config = get_bot_config()
    trainer_username = config.get("trainer_username", "willway_trainer")
    manager_username = config.get("manager_username", "willway_manager")
    
    # Логируем для отладки
    logger.info(f"Используются username: тренер - {trainer_username}, менеджер - {manager_username}")
    
    keyboard = [
        [InlineKeyboardButton("Вопрос менеджеру", url=f"https://t.me/{manager_username}")],
        [InlineKeyboardButton("Вопрос тренеру", url=f"https://t.me/{trainer_username}")],
        [InlineKeyboardButton("Назад", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Очистка данных пользователя для отладки
def clear(update: Update, context: CallbackContext) -> int:
    """Сбрасывает данные пользователя для отладки."""
    user_id = update.effective_user.id
    
    # Удаляем запись из базы данных
    session = get_session()
    user = session.query(User).filter(User.user_id == user_id).first()
    
    if user:
        session.delete(user)
        session.commit()
        update.message.reply_text("Ваши данные успешно сброшены. Используйте /start для новой регистрации.")
    else:
        update.message.reply_text("Данные не найдены. Используйте /start для регистрации.")
    
    session.close()
    return ConversationHandler.END

# Обновление конфигурации бота без перезапуска
def reload_config(update: Update, context: CallbackContext) -> int:
    """Перезагружает конфигурацию бота без перезапуска."""
    user_id = update.effective_user.id
    logger.info(f"Выполняется команда /reload_config пользователем {user_id}")
    
    # Проверяем, имеет ли пользователь право на выполнение команды (админ)
    session = get_session()
    
    # Проверяем наличие ID пользователя в таблице админов
    admin = session.query(AdminUser).filter(AdminUser.user_id == user_id).first()
    
    logger.info(f"Проверка прав администратора для пользователя {user_id}: пользователь найден в админах - {admin is not None}")
    
    if not admin:
        # Для обратной совместимости проверяем старое поле is_admin
        user = session.query(User).filter(User.user_id == user_id).first()
        if user and user.is_admin:
            logger.info(f"Пользователь {user_id} найден как админ через устаревшее поле is_admin")
            # Добавляем в новую таблицу админов для будущих проверок
            new_admin = AdminUser(user_id=user_id, username=update.effective_user.username)
            session.add(new_admin)
            session.commit()
        else:
            logger.warning(f"Пользователь {user_id} пытался выполнить команду /reload_config без прав администратора")
            update.message.reply_text("У вас нет прав для выполнения этой команды.")
            session.close()
            return ConversationHandler.END
    
    # Перезагружаем конфигурацию
    logger.info(f"Пользователь {user_id} имеет права администратора, загружаем конфигурацию")
    config = get_bot_config()
    logger.info(f"Загруженная конфигурация: {config}")
    
    # Применяем конфигурацию к боту
    try:
        # Применяем настройки к боту
        applied_settings = apply_bot_config(context.bot, config)
        
        # Подготовка сообщения о конфигурации
        config_info = [
            "✅ *Конфигурация успешно перезагружена!*\n",
            f"🤖 *Имя бота:* {config.get('bot_name', 'WillWay Bot')}",
        ]
        
        # Добавляем об "О боте" текст, если он есть
        if config.get('about_text'):
            config_info.append(f"ℹ️ *О боте:* {config.get('about_text')}")
        
        # Добавляем описание, если оно есть
        if config.get('description'):
            config_info.append(f"📝 *Описание:* {config.get('description')}")
        
        # Добавляем информацию о канале
        channel_url = config.get('channel_url')
        if channel_url:
            config_info.append(f"\n📢 *Канал бота:* {channel_url}")
        
        # Добавляем информацию о тренере и менеджере
        config_info.append(f"\n👨‍🏫 *Тренер:* @{config.get('trainer_username', 'не указан')}")
        config_info.append(f"👨‍💼 *Менеджер:* @{config.get('manager_username', 'не указан')}")
        
        # Добавляем информацию о командах
        if 'commands' in config and config['commands']:
            config_info.append("\n*Команды бота:*")
            for cmd, desc in config.get('commands', {}).items():
                config_info.append(f"{cmd} - {desc}")
            
            # Добавляем статус обновления команд
            status = "✅ Обновлены" if applied_settings.get("commands", False) else "❌ Не удалось обновить"
            config_info.append(f"_Команды бота: {status}_")
        
        # Добавляем информацию о приватности
        privacy_mode = "Включен" if config.get('privacy_mode', False) else "Выключен"
        config_info.append(f"\n🔒 *Режим приватности:* {privacy_mode}")
        
        # Отправляем информацию о текущей конфигурации
        logger.info(f"Отправляем полный ответ пользователю {user_id}")
        update.message.reply_text(
            "\n".join(config_info),
            parse_mode="Markdown"
        )
        logger.info(f"Ответ успешно отправлен пользователю {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при обновлении конфигурации бота: {e}")
        update.message.reply_text(f"Произошла ошибка при обновлении конфигурации: {str(e)}")
    
    session.close()
    return ConversationHandler.END

# Добавляем переменную для хранения истории разговоров пользователей с GPT
user_conversations = {}

# Обработчик для кнопки "Health ассистент"
def health_assistant_button(update: Update, context: CallbackContext):
    """Обработка нажатия на кнопку Health ассистент"""
    message = update.message
    user_id = message.from_user.id
    
    # Проверяем подписку (временно отключено - все пользователи имеют доступ)
    """
    session = get_session()
    user = session.query(User).filter(User.user_id == user_id).first()
    
    if not user or not user.is_subscribed:
        message.reply_text(
            "Для доступа к Health ассистенту необходимо оформить подписку.",
            reply_markup=payment_keyboard()
        )
        session.close()
        return
    
    session.close()
    """
    
    # Создаем клавиатуру для возврата
    keyboard = [[KeyboardButton("Назад")]]
    
    # Отправляем приветственное сообщение
    message.reply_text(
        "Привет! Я твой Health ассистент, специализирующийся на физическом и ментальном здоровье. "
        "Я могу помочь тебе с вопросами о тренировках, питании и общем благополучии. "
        "Просто задай свой вопрос, и я постараюсь дать персонализированный ответ.\n\n"
        "Чтобы вернуться в главное меню, нажми кнопку 'Назад'.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    
    # Инициализируем историю разговора для пользователя, если её нет
    if user_id not in user_conversations:
        user_conversations[user_id] = []

# Обработчик для текстовых сообщений в режиме Health ассистента
def handle_health_assistant_message(update: Update, context: CallbackContext):
    """Обработка сообщений для Health ассистента"""
    message = update.message
    user_id = message.from_user.id
    user_message = message.text
    
    # Проверяем, зарегистрирован ли пользователь (временно отключено)
    """
    session = get_session()
    user = session.query(User).filter(User.user_id == user_id).first()
    session.close()
    
    if not user:
        message.reply_text("Пожалуйста, сначала заполните анкету с помощью команды /start")
        return
    
    # Проверяем, есть ли у пользователя активная подписка
    if not user.is_subscribed:
        message.reply_text(
            "Для доступа к Health ассистенту необходимо оформить подписку.",
            reply_markup=payment_keyboard()
        )
        return
    """
    
    # Инициализируем историю разговора для пользователя, если её нет
    if user_id not in user_conversations:
        user_conversations[user_id] = []
    
    # Отправляем индикатор набора текста
    message.chat.send_action(action="typing")
    
    # Получаем ответ от GPT
    response = get_health_assistant_response(
        user_id, 
        user_message, 
        user_conversations[user_id]
    )
    
    # Сохраняем сообщение пользователя и ответ в истории
    user_conversations[user_id].append({"role": "user", "content": user_message})
    user_conversations[user_id].append({"role": "assistant", "content": response})
    
    # Ограничиваем историю до 10 сообщений (5 пар вопрос-ответ)
    if len(user_conversations[user_id]) > 20:
        user_conversations[user_id] = user_conversations[user_id][-20:]
    
    # Отправляем ответ пользователю
    message.reply_text(response)

# Обработчик кнопки "Назад" чтобы очищать историю разговора
def back_to_main_menu(update: Update, context: CallbackContext):
    """Возврат в главное меню"""
    message = update.message
    # Очищаем историю разговора
    user_id = message.from_user.id
    if user_id in user_conversations:
        user_conversations[user_id] = []
    
    # Отправляем главное меню
    message.reply_text(
        "Главное меню:",
        reply_markup=get_main_keyboard()
    )

def start(update: Update, context: CallbackContext) -> int:
    """Начало сбора данных о пользователе."""
    user = update.effective_user
    logger.info(f"Начало сбора данных о пользователе {user.id}")
    
    # Добавляем пользователя в базу, если его там нет
    try:
        session = get_session()
        db_user = session.query(User).filter(User.user_id == user.id).first()
        if not db_user:
            # Пользователя нет в базе, создаем новую запись
            logger.info(f"Создаем нового пользователя с ID {user.id}")
            new_user = User(
                user_id=user.id,
                username=user.username,
                registration_date=datetime.now()
            )
            session.add(new_user)
            session.commit()
        session.close()
    except Exception as e:
        logger.error(f"Ошибка при добавлении пользователя в базу: {e}")
    
    # Получаем конфигурацию бота
    config = get_bot_config()
    botpic_path = config.get('botpic_url', '')
    
    # Приветственное сообщение
    welcome_text = (
        f"Привет, {user.first_name}! 👋\n\n"
        "Я бот WillWay, ваш персональный помощник по здоровому образу жизни.\n\n"
        "Чтобы предложить вам персонализированные рекомендации, мне нужно задать несколько вопросов.\n\n"
        "Давайте начнем с вашего пола:"
    )
    
    # Отправляем приветственное сообщение с изображением (если указано) и клавиатурой
    if botpic_path and os.path.exists(os.path.abspath(botpic_path.lstrip('/'))):
        try:
            # Отправляем изображение с подписью
            update.message.reply_photo(
                photo=open(os.path.abspath(botpic_path.lstrip('/')), 'rb'),
                caption=welcome_text,
                reply_markup=gender_keyboard()
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке изображения: {e}")
            # Если не удалось отправить изображение, отправляем только текст
            update.message.reply_text(welcome_text, reply_markup=gender_keyboard())
    else:
        # Отправляем только текст, если путь к изображению не указан или файл не существует
        update.message.reply_text(welcome_text, reply_markup=gender_keyboard())
    
    return GENDER

def gender(update: Update, context: CallbackContext) -> int:
    """Сохраняем пол и запрашиваем возраст."""
    query = update.callback_query
    query.answer()
    
    user_gender = query.data
    context.user_data['gender'] = user_gender
    
    # Обновляем информацию в базе данных
    session = get_session()
    user = session.query(User).filter(User.user_id == update.effective_user.id).first()
    if user:
        user.gender = user_gender
        session.commit()
    session.close()
    
    query.edit_message_text("Отлично! Теперь укажи свой возраст (просто напиши число):")
    return AGE

def age(update: Update, context: CallbackContext) -> int:
    """Сохраняем возраст и запрашиваем рост."""
    try:
        user_age = int(update.message.text)
        context.user_data['age'] = user_age
        
        # Обновляем информацию в базе данных
        session = get_session()
        user = session.query(User).filter(User.user_id == update.effective_user.id).first()
        if user:
            user.age = user_age
            session.commit()
        session.close()
        
        update.message.reply_text("Спасибо! Теперь укажи свой рост в сантиметрах (просто напиши число):")
        return HEIGHT
    except ValueError:
        update.message.reply_text("Пожалуйста, введи возраст в виде числа (например, 30):")
        return AGE

def height(update: Update, context: CallbackContext) -> int:
    """Сохраняем рост и запрашиваем вес."""
    try:
        user_height = int(update.message.text)
        context.user_data['height'] = user_height
        
        # Обновляем информацию в базе данных
        session = get_session()
        user = session.query(User).filter(User.user_id == update.effective_user.id).first()
        if user:
            user.height = user_height
            session.commit()
        session.close()
        
        update.message.reply_text("Отлично! Теперь укажи свой вес в килограммах (просто напиши число):")
        return WEIGHT
    except ValueError:
        update.message.reply_text("Пожалуйста, введи рост в виде числа (например, 175):")
        return HEIGHT

def weight(update: Update, context: CallbackContext) -> int:
    """Сохраняем вес и запрашиваем основную цель."""
    try:
        user_weight = int(update.message.text)
        context.user_data['weight'] = user_weight
        
        # Обновляем информацию в базе данных
        session = get_session()
        user = session.query(User).filter(User.user_id == update.effective_user.id).first()
        if user:
            user.weight = user_weight
            session.commit()
        session.close()
        
        # Инициализируем список выбранных целей
        context.user_data['selected_goals'] = []
        
        update.message.reply_text(
            "Какая твоя основная цель? (выбери свой вариант, можно выбрать несколько из списка):",
            reply_markup=main_goal_keyboard()
        )
        return MAIN_GOAL
    except ValueError:
        update.message.reply_text("Пожалуйста, введи вес в виде числа (например, 70):")
        return WEIGHT

def main_goal(update: Update, context: CallbackContext) -> int:
    """Обрабатываем выбор целей с возможностью выбрать несколько."""
    query = update.callback_query
    query.answer()
    
    # Словарь соответствия callback_data и названий целей
    goal_dict = {
        'goal_1': 'Снижение веса',
        'goal_2': 'Набор мышечной массы',
        'goal_3': 'Коррекция осанки',
        'goal_4': 'Убрать дряхлость в теле',
        'goal_5': 'Общий тонус/рельеф мышц',
        'goal_6': 'Восстановиться после родов',
        'goal_7': 'Снять эмоциональное напряжение',
        'goal_8': 'Улучшить качество сна',
        'goal_9': 'Стать более энергичным'
    }
    
    if query.data == 'goals_done':
        # Проверяем, что хотя бы одна цель выбрана
        if not context.user_data.get('selected_goals'):
            query.answer("Выберите хотя бы одну цель!")
            return MAIN_GOAL
        
        # Объединяем выбранные цели в строку
        selected_goals_text = ", ".join(context.user_data['selected_goals'])
        context.user_data['main_goal'] = selected_goals_text
        
        # Обновляем информацию в базе данных
        session = get_session()
        user = session.query(User).filter(User.user_id == update.effective_user.id).first()
        if user:
            user.main_goal = selected_goals_text
            session.commit()
        session.close()
        
        # Переходим к следующему шагу
        query.edit_message_text(
            f"Вы выбрали цели: {selected_goals_text}\n\nКакая дополнительная цель?",
            reply_markup=additional_goal_keyboard()
        )
        return ADDITIONAL_GOAL
    
    # Обрабатываем выбор цели
    goal_key = query.data
    if goal_key in goal_dict:
        goal_name = goal_dict[goal_key]
        
        # Добавляем или удаляем цель из списка
        if goal_name not in context.user_data.get('selected_goals', []):
            context.user_data.setdefault('selected_goals', []).append(goal_name)
            emoji = "✅"
        else:
            context.user_data['selected_goals'].remove(goal_name)
            emoji = "☑️"
        
        # Подготавливаем текущий список выбранных целей для отображения
        selected_goals = context.user_data.get('selected_goals', [])
        goals_text = "Текущие выбранные цели:\n" + "\n".join([f"• {goal}" for goal in selected_goals]) if selected_goals else "Цели пока не выбраны"
        
        # Обновляем клавиатуру с отмеченными целями
        keyboard = []
        for g_key, g_name in goal_dict.items():
            prefix = "✅" if g_name in selected_goals else "☑️"
            keyboard.append([InlineKeyboardButton(f"{prefix} {g_name}", callback_data=g_key)])
        
        keyboard.append([InlineKeyboardButton("Готово ✓", callback_data="goals_done")])
        
        # Отправляем обновленную клавиатуру
        query.edit_message_text(
            f"{goals_text}\n\nВыберите ваши цели (можно несколько):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MAIN_GOAL
    
    return MAIN_GOAL

def additional_goal(update: Update, context: CallbackContext) -> int:
    """Сохраняем дополнительную цель и запрашиваем формат работы."""
    query = update.callback_query
    query.answer()
    
    user_additional_goal = query.data
    context.user_data['additional_goal'] = user_additional_goal
    
    # Обновляем информацию в базе данных
    session = get_session()
    user = session.query(User).filter(User.user_id == update.effective_user.id).first()
    if user:
        user.additional_goal = user_additional_goal
        session.commit()
    session.close()
    
    query.edit_message_text(
        "Какой у тебя формат работы?",
        reply_markup=work_format_keyboard()
    )
    return WORK_FORMAT

def work_format(update: Update, context: CallbackContext) -> int:
    """Сохраняем формат работы и запрашиваем частоту занятий спортом."""
    query = update.callback_query
    query.answer()
    
    user_work_format = query.data
    context.user_data['work_format'] = user_work_format
    
    # Обновляем информацию в базе данных
    session = get_session()
    user = session.query(User).filter(User.user_id == update.effective_user.id).first()
    if user:
        user.work_format = user_work_format
        session.commit()
    session.close()
    
    query.edit_message_text(
        "Как часто занимаешься спортом?",
        reply_markup=sport_frequency_keyboard()
    )
    return SPORT_FREQUENCY

def sport_frequency(update: Update, context: CallbackContext) -> int:
    """Сохраняем частоту занятий спортом и переходим к вводу email."""
    query = update.callback_query
    query.answer()
    
    user_sport_frequency = query.data
    context.user_data['sport_frequency'] = user_sport_frequency
    
    # Обновляем информацию в базе данных
    session = get_session()
    user = session.query(User).filter(User.user_id == update.effective_user.id).first()
    if user:
        user.sport_frequency = user_sport_frequency
        session.commit()
    session.close()
    
    # Переходим к вводу email
    query.edit_message_text(
        "Спасибо за предоставленную информацию! 👍\n\n"
        "Теперь нам нужны данные для регистрации аккаунта.\n\n"
        "Пожалуйста, введите ваш email:"
    )
    return EMAIL

def email(update: Update, context: CallbackContext) -> int:
    """Сохраняем email и переходим к вводу телефона."""
    user_email = update.message.text.strip()
    
    # Простая валидация email
    if '@' not in user_email or '.' not in user_email:
        update.message.reply_text("Пожалуйста, введите корректный email:")
        return EMAIL
    
    context.user_data['email'] = user_email
    
    # Обновляем информацию в базе данных
    session = get_session()
    user = session.query(User).filter(User.user_id == update.effective_user.id).first()
    if user:
        user.email = user_email
        session.commit()
    session.close()
    
    # Переходим к вводу телефона
    update.message.reply_text(
        "Теперь, пожалуйста, введите ваш номер телефона в формате +7XXXXXXXXXX:"
    )
    return PHONE

def phone(update: Update, context: CallbackContext) -> int:
    """Сохраняем телефон и переходим к созданию пароля."""
    user_phone = update.message.text.strip()
    
    # Простая валидация телефона
    if not (user_phone.startswith('+7') or user_phone.startswith('8')) or len(user_phone.replace('+', '').replace('-', '').replace(' ', '')) < 10:
        update.message.reply_text("Пожалуйста, введите корректный номер телефона в формате +7XXXXXXXXXX:")
        return PHONE
    
    context.user_data['phone'] = user_phone
    
    # Обновляем информацию в базе данных
    session = get_session()
    user = session.query(User).filter(User.user_id == update.effective_user.id).first()
    if user:
        user.phone = user_phone
        session.commit()
    session.close()
    
    # Переходим к созданию пароля
    update.message.reply_text(
        "Отлично! Теперь придумайте пароль для вашего аккаунта (минимум 6 символов):"
    )
    return PASSWORD

def password(update: Update, context: CallbackContext) -> int:
    """Сохраняем пароль и переходим к оплате."""
    user_password = update.message.text.strip()
    
    # Простая валидация пароля
    if len(user_password) < 6:
        update.message.reply_text("Пароль должен содержать минимум 6 символов. Попробуйте еще раз:")
        return PASSWORD
    
    context.user_data['password'] = user_password
    
    # Обновляем информацию в базе данных
    session = get_session()
    user = session.query(User).filter(User.user_id == update.effective_user.id).first()
    if user:
        user.password = user_password
        user.registered = True  # Отмечаем, что регистрация завершена
        session.commit()
    session.close()
    
    # Отправляем информацию о вариантах подписки
    update.message.reply_text(
        "Регистрация успешно завершена! 👍\n\n"
        "Теперь выберите подходящий тариф для доступа к Health ассистенту:",
        reply_markup=payment_keyboard()
    )
    
    # Синхронизируем данные с Airtable
    sync_user_with_airtable(update.effective_user.id)
    
    return PAYMENT

# Функция для синхронизации данных пользователя с Airtable
def sync_user_with_airtable(user_id):
    """Синхронизирует данные пользователя с Airtable."""
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_TABLE_ID:
        logger.warning(f"Airtable API не инициализирован, синхронизация для пользователя {user_id} не выполнена")
        return False
    
    try:
        # Используем прямые запросы к API вместо библиотеки
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            logger.warning(f"Пользователь {user_id} не найден в БД для синхронизации с Airtable")
            session.close()
            return False
        
        # Данные для Airtable с минимальным набором полей и правильными именами
        record_data = {
            'fields': {
                'Email': user.email or "",
                'Номер телефона ': user.phone or "",  # Пробел в конце!
                'Имя': user.username or "Без имени"
            }
        }
        
        logger.info(f"Подготовлены данные для отправки в Airtable для пользователя {user_id}")
        
        # Прямые запросы к API
        headers = {
            'Authorization': f'Bearer {AIRTABLE_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Проверяем, есть ли уже запись в Airtable по Email
        url = f'https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}'
        filter_formula = f"{{Email}}='{user.email}'" if user.email else None
        
        try:
            # Если у нас есть email для поиска
            if filter_formula:
                existing_records_response = requests.get(
                    f"{url}?filterByFormula={filter_formula}",
                    headers=headers
                )
                
                if existing_records_response.status_code != 200:
                    logger.error(f"Ошибка API Airtable: {existing_records_response.status_code} - {existing_records_response.text}")
                    raise Exception(f"API вернул код {existing_records_response.status_code}")
                    
                existing_records = existing_records_response.json().get('records', [])
                
                if existing_records:
                    # Обновляем существующую запись
                    record_id = existing_records[0]['id']
                    update_response = requests.patch(
                        f"{url}/{record_id}",
                        headers=headers,
                        json=record_data
                    )
                    
                    if update_response.status_code not in [200, 201, 204]:
                        logger.error(f"Ошибка обновления в Airtable: {update_response.status_code} - {update_response.text}")
                        raise Exception(f"API вернул код {update_response.status_code}")
                        
                    logger.info(f"Обновлена запись в Airtable для пользователя {user_id}")
                else:
                    # Создаем новую запись
                    create_response = requests.post(
                        url,
                        headers=headers,
                        json={"records": [record_data]}
                    )
                    
                    if create_response.status_code not in [200, 201, 204]:
                        logger.error(f"Ошибка создания в Airtable: {create_response.status_code} - {create_response.text}")
                        raise Exception(f"API вернул код {create_response.status_code}")
                        
                    logger.info(f"Создана запись в Airtable для пользователя {user_id}")
            else:
                # Если у пользователя нет email, создаем новую запись
                create_response = requests.post(
                    url,
                    headers=headers,
                    json={"records": [record_data]}
                )
                
                if create_response.status_code not in [200, 201, 204]:
                    logger.error(f"Ошибка создания в Airtable: {create_response.status_code} - {create_response.text}")
                    raise Exception(f"API вернул код {create_response.status_code}")
                    
                logger.info(f"Создана запись в Airtable для пользователя {user_id}")
            
            # Отмечаем, что синхронизация выполнена
            user.airtable_synced = True
            session.commit()
            session.close()
            return True
            
        except Exception as airtable_error:
            logger.error(f"Ошибка при работе с Airtable: {airtable_error}")
            session.close()
            return False
            
    except Exception as e:
        logger.error(f"Общая ошибка при синхронизации с Airtable: {e}")
        if 'session' in locals():
            session.close()
        return False

def payment(update: Update, context: CallbackContext) -> int:
    """Обрабатываем выбор тарифа."""
    query = update.callback_query
    query.answer()
    
    subscription_type = query.data
    
    # Генерируем ссылку на оплату
    if subscription_type == "monthly":
        amount = 2222.0
        amount_display = "2,222р"
        days = 30
    else:  # yearly
        amount = 17777.0
        amount_display = "17,777р"
        days = 365
    
    # Подготовка данных пользователя для платежной системы
    user_id = update.effective_user.id
    
    session = get_session()
    user = session.query(User).filter(User.user_id == user_id).first()
    
    # Проверяем, завершил ли пользователь регистрацию
    if not user or not user.registered:
        query.edit_message_text(
            "Для оформления подписки необходимо сначала завершить регистрацию. "
            "Пожалуйста, начните регистрацию заново, отправив команду /start"
        )
        session.close()
        return ConversationHandler.END
    
    user_data = {
        'user_id': str(user_id),
        'username': update.effective_user.username or "",
        'email': user.email or "",
        'phone': user.phone or ""
    }
    session.close()
    
    # Используем адаптер для создания платежа, если он доступен
    payment_info = None
    if payment_adapter:
        try:
            logger.info(f"Создание платежа через CloudPayments для пользователя {user_id}")
            payment_info = payment_adapter.generate_payment_link(
                amount=amount,
                subscription_type=subscription_type,
                user_data=user_data
            )
            logger.info(f"Получена информация о платеже: {payment_info}")
            
            if isinstance(payment_info, dict) and 'payment_url' in payment_info:
                payment_link = payment_info['payment_url']
                # Сохраняем ID платежа для последующей проверки
                context.user_data['payment_id'] = payment_info.get('payment_id', '')
            else:
                payment_link = payment_info  # Ссылка-заглушка
        except Exception as e:
            logger.error(f"Ошибка при создании платежа: {e}")
            payment_link = f"https://link-to-payment-{subscription_type}.com"  # Заглушка
    else:
        # Используем заглушки, если адаптер недоступен
        payment_link = f"https://link-to-payment-{subscription_type}.com"
    
    context.user_data['subscription_type'] = subscription_type
    context.user_data['payment_amount'] = amount_display
    context.user_data['subscription_days'] = days
    
    # Отправляем инструкции по оплате
    query.edit_message_text(
        f"Вы выбрали подписку на {'месяц' if subscription_type == 'monthly' else 'год'} стоимостью {amount_display}.\n\n"
        f"Для оплаты перейдите по ссылке: {payment_link}\n\n"
        "После успешной оплаты вы получите доступ к Health ассистенту."
    )
    
    # Создаем кнопки для проверки статуса платежа и отмены
    keyboard = [
        [InlineKeyboardButton("Проверить статус оплаты", callback_data="check_payment")],
        [InlineKeyboardButton("Отмена", callback_data="cancel_payment")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    context.bot.send_message(
        chat_id=update.effective_user.id,
        text="После оплаты нажмите кнопку 'Проверить статус оплаты'",
        reply_markup=reply_markup
    )
    
    return ConversationHandler.END

# Новая функция для обработки callback проверки платежа
def check_payment_callback(update: Update, context: CallbackContext):
    """Обработка callback для проверки статуса платежа."""
    query = update.callback_query
    query.answer()
    
    if query.data == "cancel_payment":
        query.edit_message_text("Оплата отменена. Вы можете попробовать снова позже.")
        return
    
    user_id = update.effective_user.id
    payment_id = context.user_data.get('payment_id', '')
    
    # ТЕСТОВЫЙ РЕЖИМ: Эмуляция успешного платежа без CloudPayments
    if query.data == "test_payment":
        logger.info(f"ТЕСТОВЫЙ РЕЖИМ: Эмуляция успешного платежа для пользователя {user_id}")
        confirm_payment(update, context)
        query.edit_message_text("ТЕСТОВЫЙ РЕЖИМ: Оплата успешно подтверждена! Ваша подписка активирована.")
        return
    
    # Проверяем статус платежа через адаптер
    payment_success = False
    if payment_adapter and payment_id:
        try:
            logger.info(f"Проверка статуса платежа {payment_id} для пользователя {user_id}")
            payment_success = payment_adapter.check_payment_status(payment_id)
            logger.info(f"Статус платежа {payment_id}: {'успешно' if payment_success else 'не оплачен'}")
        except Exception as e:
            logger.error(f"Ошибка при проверке статуса платежа: {e}")
    
    if payment_success:
        # Подтверждаем платеж, если он успешен
        confirm_payment(update, context)
        query.edit_message_text("Оплата успешно подтверждена! Ваша подписка активирована.")
    else:
        # Если платеж не найден или не оплачен, предлагаем проверить позже
        keyboard = [
            [InlineKeyboardButton("Проверить снова", callback_data="check_payment")],
            [InlineKeyboardButton("Отмена", callback_data="cancel_payment")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            "Платеж еще не подтвержден. Пожалуйста, убедитесь, что вы завершили оплату.",
            reply_markup=reply_markup
        )


def confirm_payment(update: Update, context: CallbackContext):
    """Подтверждение платежа и активация подписки."""
    user_id = update.effective_user.id
    subscription_type = context.user_data.get('subscription_type')
    days = context.user_data.get('subscription_days', 30)  # По умолчанию 30 дней
    payment_id = context.user_data.get('payment_id', '')
    
    # Обновляем информацию о подписке в базе данных
    session = get_session()
    user = session.query(User).filter(User.user_id == user_id).first()
    
    if user:
        user.is_subscribed = True
        user.subscription_type = subscription_type
        user.subscription_expires = datetime.now() + timedelta(days=days)
        session.commit()
    
    session.close()
    
    # Получаем конфигурацию бота для URL канала
    config = get_bot_config()
    
    # Полная синхронизация данных с Airtable, включая информацию о подписке
    try:
        sync_payment_with_airtable(user_id, subscription_type, days, payment_id)
    except Exception as e:
        logger.error(f"Ошибка при синхронизации платежа с Airtable: {e}")
    
    # Отправка приветственного сообщения и предложение вступить в канал
    channel_url = config.get('channel_url', 'https://t.me/willway_channel')
    
    # Извлекаем имя канала из URL
    channel_name = channel_url.split('/')[-1]  # Получаем последний элемент после разделения по /
    
    # Создаем клавиатуру с кнопкой для канала
    keyboard = [[InlineKeyboardButton("Присоединиться к каналу", url=channel_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Формируем текст сообщения с корректной ссылкой
    context.bot.send_message(
        chat_id=user_id,
        text="🎉 Спасибо за оплату! Ваша подписка успешно активирована.\n\n"
             "Теперь вы можете использовать Health ассистента. Рекомендуем также "
             "вступить в наш канал для получения полезных материалов и новостей:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    
    # Отправка меню с кнопками снизу
    context.bot.send_message(
        chat_id=user_id,
        text="Что бы вы хотели сделать дальше?",
        reply_markup=get_main_keyboard()
    )

# Функция для синхронизации данных о платеже с Airtable
def sync_payment_with_airtable(user_id, subscription_type, days, payment_id):
    """Синхронизирует данные о платеже с Airtable."""
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_TABLE_ID:
        logger.warning(f"Airtable API не инициализирован, синхронизация платежа {payment_id} не выполнена")
        return False
    
    try:
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            logger.warning(f"Пользователь {user_id} не найден в БД для синхронизации платежа")
            session.close()
            return False
        
        # Прямые запросы к API
        headers = {
            'Authorization': f'Bearer {AIRTABLE_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Проверяем, есть ли уже запись в Airtable по Email
        url = f'https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}'
        filter_formula = f"{{Email}}='{user.email}'" if user.email else None
        
        if not filter_formula:
            logger.warning(f"У пользователя {user_id} нет email для поиска в Airtable")
            session.close()
            return False
        
        try:
            # Сначала проверяем, существует ли запись
            existing_records_response = requests.get(
                f"{url}?filterByFormula={filter_formula}",
                headers=headers
            )
            
            if existing_records_response.status_code != 200:
                logger.error(f"Ошибка API Airtable: {existing_records_response.status_code} - {existing_records_response.text}")
                raise Exception(f"API вернул код {existing_records_response.status_code}")
                
            existing_records = existing_records_response.json().get('records', [])
            
            if not existing_records:
                # Если записи нет, создаем новую с основными данными пользователя
                logger.info(f"Запись для пользователя {user_id} не найдена в Airtable, создаем новую")
                
                # Сначала создаем запись пользователя через основную функцию синхронизации
                sync_user_with_airtable(user_id)
                
                logger.info(f"Пользователь {user_id} синхронизирован с Airtable при обработке платежа")
            else:
                logger.info(f"Пользователь {user_id} найден в Airtable при обработке платежа")
            
            # Оставляем запись о платеже в логах
            logger.info(f"Платеж для пользователя {user_id}: Тип подписки - {subscription_type}, Дней - {days}, ID платежа - {payment_id}")
            
            session.close()
            return True
            
        except Exception as airtable_error:
            logger.error(f"Ошибка при работе с Airtable для платежа: {airtable_error}")
            session.close()
            return False
            
    except Exception as e:
        logger.error(f"Общая ошибка при синхронизации платежа с Airtable: {e}")
        if 'session' in locals():
            session.close()
        return False

def handle_menu_callback(update: Update, context: CallbackContext):
    """Обработка нажатий кнопок в главном меню."""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    callback_data = query.data
    
    # Проверяем подписку для доступа к функциям
    session = get_session()
    user = session.query(User).filter(User.user_id == user_id).first()
    is_subscribed = user and user.is_subscribed
    session.close()
    
    # Health ассистент доступен только с подпиской
    if callback_data == "health_assistant":
        if not is_subscribed:
            query.edit_message_text(
                "Для доступа к Health ассистенту необходимо оформить подписку.",
                reply_markup=payment_keyboard()
            )
            return
        
        # Логика работы с Health ассистентом для оплативших пользователей
        query.edit_message_text(
            "Добро пожаловать в Health ассистент! Здесь вы сможете получить персональные рекомендации "
            "по тренировкам, питанию и образу жизни.\n\n"
            "Пожалуйста, используйте кнопку 'Health ассистент' в нижней панели для начала диалога с ассистентом.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_to_menu")]])
        )
    
    # Управление подпиской
    elif callback_data == "subscription_management":
        if not is_subscribed:
            query.edit_message_text(
                "Управление подпиской доступно только для пользователей с активной подпиской. "
                "Пожалуйста, оформите подписку.",
                reply_markup=payment_keyboard()
            )
            return
            
        query.edit_message_text(
            "Функция управления подпиской находится в разработке и будет доступна в ближайшее время.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_to_menu")]])
        )
    
    # Связь с поддержкой доступна для всех
    elif callback_data == "support":
        # Всегда запрашиваем новую клавиатуру, чтобы получить актуальные username
        logger.info("Открыт раздел поддержки, создаем клавиатуру...")
        support_kb = support_keyboard()
        query.edit_message_text(
            "Выберите тип поддержки:",
            reply_markup=support_kb
        )
        return SUPPORT
    
    # Пригласить друга
    elif callback_data == "invite_friend":
        if not is_subscribed:
            query.edit_message_text(
                "Функция приглашения друзей доступна только для пользователей с активной подпиской. "
                "Пожалуйста, оформите подписку.",
                reply_markup=payment_keyboard()
            )
            return
            
        query.edit_message_text(
            "Функция приглашения друзей находится в разработке и будет доступна в ближайшее время.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_to_menu")]])
        )
    
    # Возврат в основное меню
    elif callback_data == "back_to_menu":
        query.edit_message_text(
            "Главное меню:",
            reply_markup=menu_keyboard()
        )

def cancel(update: Update, context: CallbackContext) -> int:
    """Отмена регистрации."""
    update.message.reply_text('Регистрация отменена.')
    return ConversationHandler.END

# Обработчик для текстовых сообщений кнопок в главном меню
def handle_text_messages(update, context):
    """Обрабатывает текстовые сообщения из основного меню."""
    text = update.message.text
    user_id = update.effective_user.id
    logger.info(f"Пользователь {user_id} отправил текст: {text}")
    
    # Проверяем подписку
    session = get_session()
    user = session.query(User).filter(User.user_id == user_id).first()
    is_subscribed = user and user.is_subscribed
    session.close()

    # Создаем клавиатуру напрямую
    keyboard = [
        [KeyboardButton("Health ассистент")],
        [KeyboardButton("Управление подпиской")],
        [KeyboardButton("Связь с поддержкой")],
        [KeyboardButton("Пригласить друга")]
    ]
    
    main_kb = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    if text == "Health ассистент":
        if not is_subscribed:
            update.message.reply_text(
                "Для доступа к Health ассистенту требуется подписка. Пожалуйста, оформите подписку.",
                reply_markup=main_kb
            )
            return
        
        # Активируем GPT-ассистента только для оплативших пользователей
        health_assistant_button(update, context)
        
    elif text == "Управление подпиской":
        if not is_subscribed:
            update.message.reply_text(
                "Управление подпиской доступно только для пользователей с активной подпиской.",
                reply_markup=main_kb
            )
            return
            
        update.message.reply_text(
            "Управление подпиской находится в разработке. Скоро эта функция будет доступна!", 
            reply_markup=main_kb
        )
        
    elif text == "Связь с поддержкой":
        # Доступно для всех пользователей
        logger.info(f"Пользователь {user_id} выбрал связь с поддержкой")
        # Создаем клавиатуру поддержки напрямую
        support_keyboard = [
            [KeyboardButton("Связаться с тренером")],
            [KeyboardButton("Связаться с менеджером")],
            [KeyboardButton("Меню ✅")]
        ]
        support_kb = ReplyKeyboardMarkup(support_keyboard, resize_keyboard=True)
        
        update.message.reply_text(
            "Выберите, с кем вы хотите связаться:", 
            reply_markup=support_kb
        )
        
    elif text == "Пригласить друга":
        if not is_subscribed:
            update.message.reply_text(
                "Функция приглашения друзей доступна только для пользователей с активной подпиской.",
                reply_markup=main_kb
            )
            return
            
        update.message.reply_text(
            "Функция 'Пригласить друга' находится в разработке. Скоро вы сможете поделиться ботом с друзьями!", 
            reply_markup=main_kb
        )
    elif text == "Меню ✅":
        update.message.reply_text(
            "Вы вернулись в главное меню.", 
            reply_markup=main_kb
        )
    elif text == "😊 Анекдот":
        update.message.reply_text(
            "Функция анекдотов находится в разработке. Скоро я смогу рассказать вам что-нибудь смешное!", 
            reply_markup=main_kb
        )
    elif text == "Назад":
        # Обработка возврата из режима health assistant
        back_to_main_menu(update, context)
    else:
        update.message.reply_text(
            "Извините, я не понимаю эту команду. Пожалуйста, используйте кнопки меню.", 
            reply_markup=main_kb
        )

def handle_support_messages(update, context):
    """Обрабатывает сообщения от кнопок поддержки."""
    text = update.message.text
    user_id = update.effective_user.id
    logger.info(f"Пользователь {user_id} в меню поддержки выбрал: {text}")

    # Создаем клавиатуру напрямую
    keyboard = [
        [KeyboardButton("Health ассистент")],
        [KeyboardButton("Управление подпиской")],
        [KeyboardButton("Связь с поддержкой")],
        [KeyboardButton("Пригласить друга")]
    ]
    
    main_kb = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    if text == "Связаться с тренером":
        # Получаем имя пользователя тренера из конфигурации
        config = get_bot_config()
        trainer_username = config.get('trainer_username', '')
        
        if trainer_username:
            update.message.reply_text(
                f"Вы можете связаться с тренером через Telegram: @{trainer_username}",
                reply_markup=main_kb
            )
        else:
            update.message.reply_text(
                "К сожалению, контактные данные тренера временно недоступны. Пожалуйста, попробуйте позже.",
                reply_markup=main_kb
            )
    
    elif text == "Связаться с менеджером":
        # Получаем имя пользователя менеджера из конфигурации
        config = get_bot_config()
        manager_username = config.get('manager_username', '')
        
        if manager_username:
            update.message.reply_text(
                f"Вы можете связаться с менеджером через Telegram: @{manager_username}",
                reply_markup=main_kb
            )
        else:
            update.message.reply_text(
                "К сожалению, контактные данные менеджера временно недоступны. Пожалуйста, попробуйте позже.",
                reply_markup=main_kb
            )
    
    elif text == "Меню ✅":
        update.message.reply_text(
            "Вы вернулись в главное меню.", 
            reply_markup=main_kb
        )

def handle_other_messages(update, context):
    """Обрабатывает все сообщения, которые не были обработаны другими обработчиками."""
    user_id = update.effective_user.id
    text = update.message.text
    logger.info(f"Получено необработанное сообщение от пользователя {user_id}: {text}")
    
# Добавляем функцию main для запуска бота
def main():
    """Запуск бота."""
    logger.info("Запуск бота...")
    
    # Проверяем переменные окружения
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("Не установлена переменная окружения BOT_TOKEN. Бот не может быть запущен.")
        return
    
    logger.info("Переменные окружения установлены корректно.")
    
    # Создаем экземпляр бота и диспетчера
    updater = Updater(token)
    dispatcher = updater.dispatcher
    
    # Определяем обработчик разговора для сбора данных
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            GENDER: [CallbackQueryHandler(gender)],
            AGE: [MessageHandler(Filters.text & ~Filters.command, age)],
            HEIGHT: [MessageHandler(Filters.text & ~Filters.command, height)],
            WEIGHT: [MessageHandler(Filters.text & ~Filters.command, weight)],
            MAIN_GOAL: [CallbackQueryHandler(main_goal)],
            ADDITIONAL_GOAL: [CallbackQueryHandler(additional_goal)],
            WORK_FORMAT: [CallbackQueryHandler(work_format)],
            SPORT_FREQUENCY: [CallbackQueryHandler(sport_frequency)],
            EMAIL: [MessageHandler(Filters.text & ~Filters.command, email)],
            PHONE: [MessageHandler(Filters.text & ~Filters.command, phone)],
            PASSWORD: [MessageHandler(Filters.text & ~Filters.command, password)],
            PAYMENT: [CallbackQueryHandler(payment)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Добавляем обработчик для сбора данных пользователя
    dispatcher.add_handler(conv_handler)
    
    # Добавляем обработчики команд
    dispatcher.add_handler(CommandHandler("help", lambda u, c: u.message.reply_text("Используйте /start для начала регистрации")))
    dispatcher.add_handler(CommandHandler("reload_config", reload_config))
    
    # Обработчик для callback проверки платежа
    dispatcher.add_handler(CallbackQueryHandler(check_payment_callback, pattern="^check_payment$|^cancel_payment$|^test_payment$"))
    
    # Добавляем обработчик для текста "Назад" в режиме GPT-ассистента
    dispatcher.add_handler(MessageHandler(
        Filters.regex('^Назад$'),
        back_to_main_menu
    ))
    
    # Добавляем обработчик текстовых сообщений - основное меню
    dispatcher.add_handler(MessageHandler(
        Filters.regex('^(Health ассистент|Управление подпиской|Связь с поддержкой|Пригласить друга)$'), 
        handle_text_messages
    ))
    
    # Добавляем обработчик для раздела поддержки
    dispatcher.add_handler(MessageHandler(
        Filters.regex('^(Связаться с тренером|Связаться с менеджером|Меню ✅)$'),
        handle_support_messages
    ))
    
    # Добавляем обработчик коллбэков меню
    dispatcher.add_handler(CallbackQueryHandler(handle_menu_callback))
    
    # Добавляем запасной обработчик для всех остальных текстовых сообщений
    dispatcher.add_handler(MessageHandler(
        Filters.text & ~Filters.command, 
        handle_other_messages
    ))
    
    # Проверяем наличие переменных окружения для запуска в режиме webhook
    webhook_url = os.getenv("WEBHOOK_BASE_URL")
    
    # Запускаем бота
    if webhook_url:
        # Запуск в режиме webhook
        port = int(os.getenv("PORT", "8443"))
        logger.info(f"Запуск бота в режиме webhook на {webhook_url}")
        updater.start_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=token,
            webhook_url=f"{webhook_url}/{token}"
        )
    else:
        # Запуск в режиме polling (локальный режим)
        logger.info("Запуск бота в режиме polling")
        updater.start_polling()
    
    logger.info("Бот запущен!")
    
    # Блокировка до прерывания работы
    updater.idle()
    