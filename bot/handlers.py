#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import json
import requests
import logging
import telegram
import pytz 
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import time
import threading
from telegram.error import BadRequest
from telegram import ParseMode
import re
import types
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Union, Any, Callable
import traceback
import random
from sqlalchemy import or_

load_dotenv()

TIMEZONE = pytz.timezone('Europe/Moscow')

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.models import User, get_session, AdminUser, MessageHistory, ReferralCode, ReferralUse, ChatHistory, Payment
from bot.gpt_assistant import get_health_assistant_response

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, Bot, ChatAction
from telegram.ext import Updater, CallbackContext, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, Filters
# Импортируем модуль обработки сомнений при подписке
from bot.subscription_doubt_handler import setup_subscription_doubt_handlers
# Импортируем модуль отмены подписки
from bot.subscription_cancel_handler import get_cancel_subscription_button, setup_subscription_cancel_handlers

import colorlog

# Определяем константы для parse_mode
MARKDOWN = "Markdown"
HTML = "HTML"

media_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'img')

def setup_colored_logging():
    handler = colorlog.StreamHandler(stream=sys.stdout)
    handler.setFormatter(colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    ))
    
    file_handler = logging.FileHandler('payment_logs.log')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    logger = logging.getLogger('root')  # Изменяем на 'root', чтобы использовать основной логгер
    logger.setLevel(logging.INFO)
    
    for hdlr in logger.handlers[:]:
        logger.removeHandler(hdlr)
    
    logger.addHandler(handler)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_colored_logging()

TOKEN = os.getenv('BOT_TOKEN')

(
    GENDER, 
    AGE, 
    HEIGHT, 
    WEIGHT, 
    MAIN_GOAL, 
    ADDITIONAL_GOAL, 
    WORK_FORMAT, 
    SPORT_FREQUENCY, 
    PAYMENT, 
    MAIN, 
    GPT_ASSISTANT,
    SUBSCRIPTION,
    SUPPORT,
    INVITE,
    MENU,
    SUPPORT_OPTIONS
) = range(16)

# API интеграции отключены
logger.info("API интеграции отключены")

BOT_CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bot_config.json')

def fix_image_paths(config):
    updates = {}
    
    desc_pic_url = config.get('description_pic_url', '')
    if desc_pic_url:
        logger.info(f"Найден путь изображения описания: {desc_pic_url}")
        
        if desc_pic_url.startswith('/'):
            clean_path = desc_pic_url[1:]
        else:
            clean_path = desc_pic_url
            
        abs_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), clean_path)
        logger.info(f"Абсолютный путь изображения описания: {abs_path}")
        
        if os.path.exists(abs_path):
            logger.info("Файл изображения описания существует")
        else:
            logger.warning(f"Файл изображения описания не найден: {abs_path}")
    
    video_url = config.get('intro_video_url', '')
    if video_url:
        logger.info(f"Найден путь к видео: {video_url}")
        
        if video_url.startswith('/'):
            clean_path = video_url[1:]
        else:
            clean_path = video_url
            
        abs_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), clean_path)
        logger.info(f"Абсолютный путь к видео: {abs_path}")
        
        if os.path.exists(abs_path):
            logger.info("Файл видео существует")
        else:
            logger.warning(f"Файл видео не найден: {abs_path}")
            # Если файл не найден, можно указать путь по умолчанию
    
    # Применяем обновления к конфигурации
    if updates:
        for key, value in updates.items():
            config[key] = value
    
    # ВАЖНОЕ ПРИМЕЧАНИЕ ДЛЯ УЛУЧШЕНИЯ КАЧЕСТВА ВИДЕО:
    # 1. Поместите видео высокого качества в папку web_admin/static/video/ 
    # 2. Назовите файл intro_video.mp4
    # 3. Рекомендуемое разрешение видео: 1280x720 (HD)
    # 4. Рекомендуемый битрейт: не менее 2-3 Мбит/с
    # 5. Формат: MP4 с кодеком H.264
    # 6. Размер файла: для лучшего качества видео может весить до 20 МБ
    # 7. После замены удалите значение 'intro_video_file_id' из bot_config.json,
    #    чтобы бот загрузил новое видео при следующем запуске
    
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
        
        # Для настроек, которые можно применить на лету в коде
        if 'privacy_mode' in config:
            # Например, можно хранить в боте настройку, которая влияет на обработку сообщений
            # бот будет использовать это значение для определения режима приватности
            applied_settings["privacy_mode"] = True
            logger.info(f"Обновлен режим приватности: {config.get('privacy_mode')}")
        
        # Используем новый модуль для обновления метаданных бота
        try:
            from bot.bot_updater import apply_bot_settings
            
            # Получаем токен бота
            token = config.get("bot_token") or os.getenv("TELEGRAM_TOKEN")
            
            if token:
                logger.info("Применяем настройки бота через API Telegram...")
                api_results = apply_bot_settings(token, config)
                
                # Обновляем результаты применения настроек
                if api_results:
                    if api_results.get("name"):
                        applied_settings["bot_name"] = True
                        logger.info("Имя бота успешно обновлено через API")
                    
                    if api_results.get("description"):
                        applied_settings["description"] = True
                        logger.info("Описание бота успешно обновлено через API")
                    
                    if api_results.get("about"):
                        applied_settings["about_text"] = True
                        logger.info("Информация 'О боте' успешно обновлена через API")
                    
                    if api_results.get("profile_photo"):
                        applied_settings["botpic"] = True
                        logger.info("Аватар бота успешно обновлен через API")
                    
                    logger.info(f"Результаты применения настроек через API: {api_results}")
                else:
                    logger.warning("Не удалось применить настройки бота через API Telegram")
            else:
                logger.warning("Не найден токен бота для применения настроек через API Telegram")
        except ImportError:
            logger.warning("Модуль bot_updater не установлен, метаданные бота не обновлены")
        except Exception as e:
            logger.error(f"Ошибка при применении настроек бота через API Telegram: {e}")
        
        return applied_settings
        
    except Exception as e:
        logger.error(f"Ошибка при применении конфигурации к боту: {e}")
        return applied_settings

# Функция для создания клавиатуры с кнопкой для открытия веб-приложения
def get_webapp_keyboard():
    """Создает клавиатуру с кнопкой для открытия внешнего веб-сайта"""
    webapp_button = InlineKeyboardButton(
        text="Открыть приложение", 
        url="https://willway.pro/members/signup"
    )
    return InlineKeyboardMarkup([[webapp_button]])

# Функция для создания главной клавиатуры (нижняя панель)
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("Health ассистент"), KeyboardButton("Управление подпиской")],
        [KeyboardButton("Связь с поддержкой"), KeyboardButton("Пригласить друга")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Функция для создания клавиатуры оплаты с добавлением ID пользователя в URL
def get_payment_keyboard(user_id, context=None):
    # Формируем URL с ID пользователя и параметрами отслеживания
    payment_url = "https://willway.pro/payment"
    
    # Добавляем UTM-метки для отслеживания источника трафика и ID пользователя
    payment_url = f"{payment_url}?tgid={user_id}"
    
    # Напоминания о незавершенной оплате отключены
    # Система оплаты не реализована
    
    keyboard = [
        [InlineKeyboardButton("Варианты WILLWAY подписки", callback_data="show_subscription_options")]
    ]
    return InlineKeyboardMarkup(keyboard)

def menu_keyboard():
    """Возвращает клавиатуру главного меню"""
    return [
        [InlineKeyboardButton("Health ассистент", callback_data="health_assistant")],
        [InlineKeyboardButton("Управление подпиской", callback_data="subscription_management")],
        [InlineKeyboardButton("Связь с поддержкой", callback_data="support")],
        [InlineKeyboardButton("Пригласить друга", callback_data="invite_friend")]
    ]

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
            parse_mode=ParseMode.MARKDOWN
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
    if update.message:
        message = update.message
        user_id = message.from_user.id
        user_first_name = message.from_user.first_name
    else:
        query = update.callback_query
        query.answer()
        message = query.message
        user_id = query.from_user.id
        user_first_name = query.from_user.first_name
    
    # Проверяем подписку через базу данных
    is_subscribed = update_subscription_status(user_id, context)
    
    if not is_subscribed:
        if update.message:
            message.reply_text(
                "Для доступа к Health ассистенту необходимо оформить подписку.",
                reply_markup=get_payment_keyboard_inline(user_id)
            )
        else:
            context.bot.send_message(
                chat_id=user_id,
                text="Для доступа к Health ассистенту необходимо оформить подписку.",
                reply_markup=get_payment_keyboard_inline(user_id)
            )
        return
    
    # Устанавливаем флаг активности Health ассистента
    context.user_data['health_assistant_active'] = True
    logger.info(f"Активирован режим Health ассистента для пользователя {user_id}")
    
    # Получаем информацию о пользователе из базы данных
    session = get_session()
    user = session.query(User).filter(User.user_id == str(user_id)).first()
    
    # Определяем какое приветствие показывать
    if user and user.health_assistant_first_time:
        # Первый запуск ассистента - показываем полное приветствие с обращением по имени
        greeting_text = (
            f"Привет {user_first_name}! Я твой личный health-ассистент WILLWAY. Помогу тебе создать здоровое подтянутое тело, улучшить ментальное состояние и внедрить новые привычки, которые реально улучшают качество жизни.\n\n"
            "Я здесь, чтобы поддерживать тебя на пути, не давая сбиться с курса, мотивировать и подсказывать, что делать на каждом этапе.\n\n"
            "Скажи с чего начнем: \n"
            "- Программа тренировок \n"
            "- Программа питания/разбор анализов \n"
            "- Программа восстановления ментального состояния."
        )
        
        # Обновляем флаг первого запуска
        user.health_assistant_first_time = False
        session.commit()
    else:
        # Повторный запуск - показываем персонализированное приветствие
        greeting_text = (
            f"Рад видеть тебя снова, {user_first_name}. В чем нужна помощь сегодня?\n"
            "- Тренировки\n"
            "- Питание\n"
            "- Ментальное состояние\n"
            "- Другой запрос"
        )
    
    session.close()
    
    # Отправляем приветствие
    if update.message:
        message.reply_text(
            greeting_text,
            reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True)
        )
    else:
        context.bot.send_message(
            chat_id=user_id,
            text=greeting_text,
            reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True)
        )
    
    # Инициализируем историю разговора для пользователя, если её нет
    if user_id not in user_conversations:
        user_conversations[user_id] = []

# Функция для получения истории сообщений пользователя из базы данных
def get_user_conversation_history(user_id, limit=10):
    """
    Получает историю сообщений пользователя из базы данных
    
    Args:
        user_id: ID пользователя в Telegram
        limit: Максимальное количество сообщений для извлечения (пар вопрос-ответ)
        
    Returns:
        list: История диалога в формате для OpenAI API
    """
    session = get_session()
    
    # Получаем последние сообщения пользователя, отсортированные по времени
    messages = session.query(MessageHistory)\
        .filter(MessageHistory.user_id == user_id)\
        .order_by(MessageHistory.timestamp.desc())\
        .limit(limit * 2)\
        .all()
    
    # Преобразуем в формат для OpenAI API и меняем порядок на хронологический
    conversation_history = [
        {"role": msg.role, "content": msg.content}
        for msg in sorted(messages, key=lambda x: x.timestamp)
    ]
    
    session.close()
    return conversation_history

# Функция для сохранения сообщения в базе данных
def save_message_to_history(user_id, role, content):
    """
    Сохраняет сообщение в историю диалога в базе данных
    
    Args:
        user_id: ID пользователя в Telegram
        role: Роль ('user' или 'assistant')
        content: Текст сообщения
    """
    session = get_session()
    
    # Создаем новую запись в базе данных
    message = MessageHistory(
        user_id=user_id,
        role=role,
        content=content
    )
    
    # Добавляем и сохраняем
    session.add(message)
    session.commit()
    session.close()

# Обработчик для текстовых сообщений в режиме Health ассистента
def handle_health_assistant_message(update: Update, context: CallbackContext):
    """Обработка сообщений для Health ассистента"""
    # Проверяем, активен ли процесс отмены подписки
    if context.user_data.get('cancellation', {}).get('active', False):
        logger.info(f"Пропуск обработки Health ассистентом - активен процесс отмены подписки")
        return
        
    # Получаем сообщение и ID пользователя
    if update.callback_query:
        message = update.callback_query.message
        user_id = update.callback_query.from_user.id
        user_message = update.callback_query.message.text
    else:
        message = update.message
        user_id = message.from_user.id
        user_message = message.text
    
    # Примечание: Обработка кнопки "Назад" перенесена в handle_text_messages
    
    # Проверяем подписку через базу данных
    is_subscribed = update_subscription_status(user_id, context)
    
    if not is_subscribed:
        # Если у пользователя нет подписки, предлагаем оформить
        response = "Для доступа к Health ассистенту необходимо оформить подписку."
        
        if update.callback_query:
            update.callback_query.message.reply_text(
                response,
                reply_markup=get_payment_keyboard_inline(user_id)
            )
        else:
            message.reply_text(
                response,
                reply_markup=get_payment_keyboard_inline(user_id)
            )
        
        # Сбрасываем флаг активности Health ассистента
        context.user_data['health_assistant_active'] = False
        return
    
    # Отправляем индикатор набора текста
    context.bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)
    
    try:
        # Получаем историю диалога из базы данных
        conversation_history = get_user_conversation_history(user_id, limit=5)
        
        # Получаем ответ от GPT
        response = get_health_assistant_response(
            user_id, 
            user_message, 
            conversation_history
        )
        
        # Сохраняем сообщение пользователя и ответ в базе данных
        save_message_to_history(user_id, "user", user_message)
        save_message_to_history(user_id, "assistant", response)
        
        # Отправляем ответ пользователю
        if update.callback_query:
            update.callback_query.message.reply_text(
                response,
                reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True)
            )
        else:
            message.reply_text(
                response,
                reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True)
            )
            
        # Поддерживаем флаг активности для следующих сообщений
        context.user_data['health_assistant_active'] = True
        logger.info(f"[HEALTH] Отправлен ответ от Health ассистента пользователю {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса к Health ассистенту: {e}")
        
        # Отправляем сообщение об ошибке
        error_message = "Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже."
        
        if update.callback_query:
            update.callback_query.message.reply_text(
                error_message,
                reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True)
            )
        else:
            message.reply_text(
                error_message,
                reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True)
            )
            
    return

# Обработчик кнопки "Назад" (не очищает историю, так как она сохраняется в базе данных)
def back_to_main_menu(update: Update, context: CallbackContext):
    """Возврат в главное меню"""
    user_id = update.effective_user.id
    
    # Определяем тип запроса (callback или обычное сообщение)
    is_callback = update.callback_query is not None
    
    # Сбрасываем флаг активности Health ассистента, если он установлен
    if context.user_data.get('health_assistant_active'):
        context.user_data['health_assistant_active'] = False
        logger.info(f"Сброшен флаг health_assistant_active при возврате в меню для пользователя {user_id}")
    
    # Проверяем, заполнил ли пользователь анкету
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        
        # Если пользователь существует, но анкета не заполнена
        if user and not user.registered:
            logger.info(f"[SURVEY_REQUIRED] Пользователь {user_id} пытается использовать меню без заполнения анкеты")
            
            # Предлагаем заполнить анкету
            keyboard = [
                [InlineKeyboardButton("Подобрать персональную программу", callback_data="start_survey")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if is_callback:
                query = update.callback_query
                query.answer()
                query.edit_message_text(
                    "Для получения доступа к функциям бота, пожалуйста, заполните анкету:",
                    reply_markup=reply_markup
                )
            else:
                update.message.reply_text(
                    "Для получения доступа к функциям бота, пожалуйста, заполните анкету:",
                    reply_markup=reply_markup
                )
            
            session.close()
            return ConversationHandler.END
        
        session.close()
        
        # Если анкета заполнена, показываем главное меню с клавиатурой внизу
        if is_callback:
            query = update.callback_query
            query.answer()
            
            # Отправляем новое сообщение с reply клавиатурой внизу
            context.bot.send_message(
                chat_id=user_id,
                text="Рад видеть вас снова! Выберите действие из меню:",
                reply_markup=get_main_keyboard()
            )
        else:
            update.message.reply_text(
                "Рад видеть вас снова! Выберите действие из меню:",
                reply_markup=get_main_keyboard()
            )
        
        # Очищаем состояние
        context.user_data.clear()
        
        return MAIN
    except Exception as e:
        logger.error(f"[SURVEY_CHECK_ERROR] Ошибка при проверке статуса анкеты: {e}")
        if 'session' in locals() and session:
            session.close()
        
        # В случае ошибки все равно показываем меню
        if is_callback:
            try:
                query = update.callback_query
                query.answer()
                
                # Отправляем новое сообщение с reply клавиатурой
                context.bot.send_message(
                    chat_id=user_id,
                    text="Рад видеть вас снова! Выберите действие из меню:",
                    reply_markup=get_main_keyboard()
                )
            except Exception as edit_error:
                logger.error(f"[MENU_ERROR] Не удалось отправить сообщение: {edit_error}")
                if update.message:
                    update.message.reply_text(
                        "Рад видеть вас снова! Выберите действие из меню:",
                        reply_markup=get_main_keyboard()
                    )
        else:
            update.message.reply_text(
                "Рад видеть вас снова! Выберите действие из меню:",
                reply_markup=get_main_keyboard()
            )
        
        return MAIN

def start(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # Добавьте эту проверку в начало функции
    # Если передан параметр /start, проверяем, может это код блогера
    if context.args and (context.args[0].startswith('ref_') and len(context.args[0]) > 8):
        from api_patch import track_referral_click  # Импортируем функцию для работы с блогерами
        
        logger.info(f"[REFERRAL] Возможный код блогера: {context.args[0]}")
        success, result = track_referral_click(context.args[0], user_id, username)
        
        if success:
            logger.info(f"[REFERRAL] Успешная обработка кода блогера: {result}")
            # Пользователь может быть новым, создадим или обновим запись
            session = get_session()
            try:
                user = session.query(User).filter(User.user_id == user_id).first()
                if not user:
                    user = User(
                        user_id=user_id,
                        username=username,
                        registration_date=datetime.now(TIMEZONE),
                        blogger_ref_code=context.args[0].replace('ref_', ''),
                        referral_source='blogger'
                    )
                    session.add(user)
                else:
                    user.blogger_ref_code = context.args[0].replace('ref_', '')
                    user.referral_source = 'blogger'
                
                session.commit()
                logger.info(f"[REFERRAL] Сохранён код блогера для пользователя {user_id}")
                
                # Перейдем к показу приветственного видео
                session.close()
                send_welcome_video(update, context)
                return ConversationHandler.END
            except Exception as e:
                session.rollback()
                logger.error(f"[REFERRAL] Ошибка при сохранении кода блогера: {str(e)}")
                session.close()
    
    # Продолжение существующего кода для обычных реферальных кодов...
    
    chat_id = update.effective_chat.id
    
    # Проверяем наличие аргументов в команде /start
    args = context.args
    referral_code = args[0] if args else None
    
    logger.info(f"[START] Пользователь {user_id} вызвал команду /start с аргументами: {args}")
    
    # Обработка параметра успешной оплаты
    if referral_code and referral_code.startswith('payment_success_'):
        try:
            # Извлекаем ID пользователя из параметра
            payment_user_id = referral_code.replace('payment_success_', '')
            logger.info(f"[PAYMENT_SUCCESS] Получен параметр успешной оплаты для пользователя {payment_user_id}")
            
            # Если ID в параметре совпадает с ID текущего пользователя
            if str(payment_user_id) == str(user_id):
                # Активируем подписку для пользователя
                session = get_session()
                user = session.query(User).filter(User.user_id == user_id).first()
                
                if user:
                    # Проверяем, не активна ли уже подписка
                    if not user.is_subscribed or (user.subscription_expires and user.subscription_expires < datetime.now(TIMEZONE)):
                        # Активируем месячную подписку
                        user.is_subscribed = True
                        user.subscription_type = "monthly"
                        user.subscription_expires = datetime.now(TIMEZONE) + timedelta(days=30)
                        user.payment_status = "completed"
                        
                        session.commit()
                        logger.info(f"[PAYMENT_SUCCESS] Активирована подписка для пользователя {user_id}")
                        
                        # Отправляем сообщение об успешной активации подписки
                        update.message.reply_text(
                            "🎉 Поздравляем! Ваша подписка успешно активирована.\n\n"
                            "Теперь вам доступны все функции бота, включая Health ассистента и персональные программы.",
                            reply_markup=get_main_keyboard()
                        )
                        
                        # Отправляем сообщения об успешной оплате
                        send_successful_payment_messages(update, context, "active")
                    else:
                        logger.info(f"[PAYMENT_SUCCESS] Подписка уже активна для пользователя {user_id}")
                        update.message.reply_text(
                            "У вас уже есть активная подписка! Спасибо за использование нашего сервиса.",
                            reply_markup=get_main_keyboard()
                        )
                    
                    # Показываем меню в любом случае
                    update.message.reply_text(
                        "Рад видеть вас снова! Выберите действие из меню:",
                        reply_markup=get_main_keyboard()
                    )
                    
                    session.close()
                    return ConversationHandler.END
                
                session.close()
            else:
                logger.warning(f"[PAYMENT_SUCCESS] Несоответствие ID пользователей: параметр {payment_user_id}, фактический {user_id}")
        except Exception as e:
            logger.error(f"[PAYMENT_SUCCESS] Ошибка при обработке успешной оплаты: {str(e)}")
    
    if referral_code:
        logger.info(f"[REFERRAL] Обнаружен реферальный код: {referral_code}")
    
    # Получаем данные о пользователе
    session = get_session()
    user_created = False
    ref_code = None  # Инициализируем переменную ref_code
    
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        
        # Если пользователь новый, создаем запись
        if not user:
            user_created = True
            user = User(
                user_id=user_id,
                username=username,
                registration_date=datetime.now(TIMEZONE),
                first_interaction_time=datetime.now(TIMEZONE),
                registered=False  # Устанавливаем флаг что пользователь не прошел регистрацию
            )
            
            # Если передан реферальный код, обрабатываем его
            if referral_code:
                # Проверяем существование кода
                ref_code = session.query(ReferralCode).filter(
                    or_(
                        ReferralCode.code == referral_code,  # Оригинальный код
                        ReferralCode.code == referral_code.replace('ref_', ''),  # Без префикса
                        ReferralCode.code == f"ref_{referral_code.replace('ref_', '')}"  # С префиксом
                    ),
                    ReferralCode.is_active == True
                ).first()
                if ref_code and str(ref_code.user_id) != str(user_id):  # Проверяем по строке для корректного сравнения
                    logger.info(f"[REFERRAL] Найден активный реферальный код: {referral_code}, владелец: {ref_code.user_id}")
                    
                    # Получаем реферера (пользователя, который пригласил текущего)
                    referrer = session.query(User).filter_by(id=ref_code.user_id).first()
                    if not referrer:
                        # Если не нашли по ID, ищем по telegram_id
                        referrer_telegram_id = session.query(User).filter_by(user_id=ref_code.user_id).first()
                        if referrer_telegram_id:
                            referrer = referrer_telegram_id
                    
                    if referrer:
                        logger.info(f"[REFERRAL] Найден реферер: id={referrer.id}, user_id={referrer.user_id}, username={referrer.username}")
                        
                        # Сохраняем связь между пользователями
                        user.referrer_id = referrer.user_id
                        user.referral_source = 'link'
                        
                        # Добавляем нового пользователя, чтобы получить его ID
                        session.add(user)
                        session.flush()  # Принудительная запись для получения ID
                        
                        logger.info(f"[REFERRAL] Создается запись использования реферальной ссылки: code_id={ref_code.id}, user_id={user.id}, referrer_id={referrer.id}")
                        
                        # Создаем запись об использовании реферального кода
                        try:
                            ref_use = ReferralUse(
                                    code_id=ref_code.id,  # Обновленное название поля
                                    user_id=user.id,
                                    referrer_id=referrer.id,
                                    created_at=datetime.now(),  # Обновленное название поля
                                    subscription_purchased=False
                            )
                            session.add(ref_use)
                            logger.info(f"[REFERRAL] Создана запись использования реферальной ссылки с обновленной структурой")
                        except Exception as ref_use_error:
                            logger.error(f"[REFERRAL_ERROR] Ошибка при создании записи использования с обновленной структурой: {str(ref_use_error)}")
                            # Пробуем создать с прежней структурой
                            try:
                                ref_use = ReferralUse(
                                    referral_code_id=ref_code.id,
                                    user_id=user.id,
                                    referrer_id=referrer.id,
                                    referred_id=int(user_id),  # Для обратной совместимости
                                    used_at=datetime.now(),
                                    subscription_purchased=False,
                                    status='registered'  # Для обратной совместимости
                                )
                                session.add(ref_use)
                                logger.info(f"[REFERRAL] Создана запись использования реферальной ссылки со старой структурой")
                            except Exception as old_error:
                                logger.error(f"[REFERRAL_ERROR] Ошибка при создании записи со старой структурой: {str(old_error)}")
                        
                        # Увеличиваем счетчик использований кода
                        try:
                            if hasattr(ref_code, 'total_uses'):
                                ref_code.total_uses += 1
                                logger.info(f"[REFERRAL] Увеличен счетчик использований кода")
                        except Exception as counter_error:
                            logger.warning(f"[REFERRAL_WARNING] Не удалось увеличить счетчик использований: {str(counter_error)}")
                        
                        logger.info(f"[REFERRAL] Пользователь {user_id} пришел по реферальной ссылке от пользователя {referrer.user_id}")
                    else:
                        logger.warning(f"[REFERRAL] Реферер с user_id={ref_code.user_id} не найден в базе данных")
                        user.referral_source = 'unknown'
                else:
                    if ref_code:
                        logger.info(f"[REFERRAL] Реферальный код принадлежит самому пользователю или недействителен")
                    else:
                        logger.info(f"[REFERRAL] Реферальный код {referral_code} не найден")
                    user.referral_source = 'direct'
                    logger.info(f"[REFERRAL] Пользователь {user_id} использовал недействительный реферальный код: {referral_code}")
            else:
                user.referral_source = 'direct'
                logger.info(f"[REFERRAL] Пользователь {user_id} пришел напрямую, без реферального кода")
        
        session.add(user)
        session.commit()
        
        if user_created:
            logger.info(f"Создан новый пользователь: {user_id}")
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка при обработке команды /start: {str(e)}")
        logger.exception(e)
    finally:
        session.close()
    
    user = None
    
    try:
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        session.close()
    except Exception as e:
        logger.error(f"Ошибка при повторном получении пользователя: {str(e)}")
    
    # Проверяем, если пользователь новый или незарегистрированный
    if user and not user.registered:
        # Отправляем только приветственное видео
        send_welcome_video(update, context)
        
        # Если администратор - показываем сообщение об этом
        if is_admin(user_id):
            logger.info(f"Пользователь {user_id} является администратором")
            update.message.reply_text(
                "Вы авторизованы как администратор. Используйте /admin для доступа к панели управления.",
                reply_markup=get_main_keyboard()
            )
            return ConversationHandler.END
        
        # Больше не отправляем сообщение о необходимости пройти опрос
        # и не запускаем автоматически анкетирование
        
        return ConversationHandler.END
    else:
        # Для уже зарегистрированных пользователей показываем главное меню
        update.message.reply_text(
            "Рад видеть вас снова! Выберите действие из меню:",
            reply_markup=get_main_keyboard()
        )
        
        if user and user.payment_status == 'pending' and not user.is_subscribed:
            schedule_payment_reminder(context, user_id)
        
        return ConversationHandler.END

def send_welcome_video(update, context):
    config = get_bot_config()
    
    keyboard = [
        [InlineKeyboardButton("Подобрать персональную программу", callback_data="start_survey")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    caption = "Мы знаем, как улучшить твоё здоровье, тело, состояние и качество жизни\n\nДай нам 2 минуты, и мы покажем как это работает"
    
    try:
        video_file_id = config.get('intro_video_file_id')
        
        video_settings = config.get('video_settings', {})
        width = video_settings.get('width', 1280)
        height = video_settings.get('height', 720)
        supports_streaming = video_settings.get('supports_streaming', True)
        timeout = video_settings.get('timeout', 120)
        disable_notification = video_settings.get('disable_notification', False)
        
        if video_file_id:
            logger.info(f"Используем сохраненный file_id для отправки видео: {video_file_id}")
            
            try:
                update.message.reply_video(
                    video=video_file_id,
                    caption=caption,
                    timeout=timeout,
                    width=width,
                    height=height,
                    supports_streaming=supports_streaming,
                    disable_notification=disable_notification,
                    parse_mode=telegram.ParseMode.HTML,
                    reply_markup=reply_markup
                )
                return
            except Exception as vid_err:
                logger.error(f"Ошибка при использовании сохраненного file_id: {vid_err}. Загружаем файл заново.")
        
        video_path = config.get('intro_video_url', '')
        
        if video_path and video_path.startswith('/'):
            clean_path = video_path[1:]
            abs_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), clean_path)
            logger.info(f"Попытка отправки видео из: {abs_path}")
            
            if os.path.exists(abs_path):
                logger.info(f"Видео файл существует, отправляем...")
                try:
                    message = update.message.reply_video(
                        video=open(abs_path, 'rb'),
                        caption=caption,
                        timeout=timeout,
                        width=width,
                        height=height,
                        supports_streaming=supports_streaming,
                        disable_notification=disable_notification,
                        parse_mode=telegram.ParseMode.HTML,
                        reply_markup=reply_markup
                    )
                    
                    if message and message.video:
                        new_file_id = message.video.file_id
                        logger.info(f"Получен новый file_id для видео: {new_file_id}")
                        
                        try:
                            config['intro_video_file_id'] = new_file_id
                            save_bot_config(config)
                            logger.info("File ID видео успешно сохранен в конфигурации")
                        except Exception as save_err:
                            logger.error(f"Ошибка при сохранении file_id в конфигурации: {save_err}")
                except telegram.error.NetworkError as network_err:
                    logger.error(f"Сетевая ошибка при отправке видео: {network_err}")
                    update.message.reply_text(
                        caption,
                        reply_markup=reply_markup
                    )
                except telegram.error.TimedOut as timeout_err:
                    logger.error(f"Таймаут при отправке видео: {timeout_err}")
                    update.message.reply_text(
                        caption,
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    logger.error(f"Неизвестная ошибка при отправке видео: {e}")
                    update.message.reply_text(
                        caption,
                        reply_markup=reply_markup
                    )
            else:
                logger.error(f"Файл видео не найден по пути: {abs_path}")
                update.message.reply_text(
                    caption,
                    reply_markup=reply_markup
                )
        else:
            logger.error(f"Некорректный путь к видео в конфигурации: {video_path}")
            update.message.reply_text(
                caption,
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Ошибка при отправке видео: {e}")
        update.message.reply_text(
            caption,
            reply_markup=reply_markup
        )

def send_survey_prompt(context: CallbackContext):
    # Убираем старый код, который отправляет дополнительное сообщение
    # Просто логируем действие
    logger.info(f"send_survey_prompt вызван, но ничего не делает согласно новым требованиям")
    # Оставляем эту функцию пустой, чтобы не отправлять дополнительное сообщение
    return

def start_survey(update: Update, context: CallbackContext) -> int:

    if update.callback_query:
        query = update.callback_query
        query.answer()  # Отвечаем на callback
        user_id = query.from_user.id
        chat_id = query.message.chat_id
    else:
        user_id = update.message.from_user.id
        chat_id = update.message.chat_id
    
    logger.info(f"[SURVEY] Пользователь {user_id} запустил анкетирование")
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if user and user.registered:
            logger.info(f"[SURVEY] Пользователь {user_id} уже заполнил анкету ранее")
            
            message_text = (
                "Ты уже заполнил анкету! Твои персональные рекомендации готовы.\n\n"
                "Ты можешь воспользоваться другими функциями бота."
            )
            
            if update.callback_query:
                query.edit_message_text(
                    text=message_text,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Вернуться в меню", callback_data="back_to_menu")]
                    ])
                )
            else:
                update.message.reply_text(
                    message_text,
                    reply_markup=get_main_keyboard()
                )
            
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"[SURVEY] Ошибка при проверке статуса анкеты: {e}")
    finally:
        session.close()
    
    context.user_data['bot_messages'] = []
    
    keyboard = [
        [InlineKeyboardButton("Мужской", callback_data="male")],
        [InlineKeyboardButton("Женский", callback_data="female")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Используем изображение 1_POL.jpg для первого вопроса
    image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'img', '1_POL.jpg')
    
    try:
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                if update.callback_query:
                    bot_message = context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption="Выберите ваш пол:",
                        reply_markup=reply_markup
                    )
                else:
                    bot_message = context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption="Выберите ваш пол:",
                        reply_markup=reply_markup
                    )
                logger.info(f"[SURVEY_START] Отправлено фото с запросом пола пользователю {user_id}")
        else:
            logger.warning(f"[SURVEY_ERROR] Файл изображения не найден: {image_path}")
            if update.callback_query:
                bot_message = context.bot.send_message(
                    chat_id=chat_id,
                    text=f"Выберите ваш пол:",
                    reply_markup=reply_markup
                )
            else:
                bot_message = context.bot.send_message(
                    chat_id=chat_id,
                    text=f"Выберите ваш пол:",
                    reply_markup=reply_markup
                )
    except Exception as e:
        logger.error(f"[SURVEY_ERROR] Ошибка при отправке изображения пола: {e}")
        if update.callback_query:
            bot_message = context.bot.send_message(
                chat_id=chat_id,
                text=f"Выберите ваш пол:",
                reply_markup=reply_markup
            )
        else:
            bot_message = context.bot.send_message(
                chat_id=chat_id,
                text=f"Выберите ваш пол:",
                reply_markup=reply_markup
            )
    
    context.user_data['bot_messages'].append(bot_message.message_id)
    
    return GENDER

def gender(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    
    user_gender = query.data
    user_id = update.effective_user.id
    message_id = query.message.message_id
    
    logger.info(f"[SURVEY_GENDER_DEBUG] Пользователь {user_id} выбрал пол: {user_gender}, message_id: {message_id}")
    
    context.user_data['gender'] = "Мужской" if user_gender == "male" else "Женский"
    logger.info(f"[SURVEY_GENDER] Пользователь {user_id} выбрал пол: {context.user_data['gender']}")
    
    try:
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        if user:
            user.gender = context.user_data['gender']
            session.commit()
            logger.info(f"[SURVEY_GENDER] Данные о поле пользователя {user_id} сохранены в БД")
        session.close()
    except Exception as e:
        logger.error(f"[SURVEY_GENDER_ERROR] Ошибка при сохранении пола в БД: {e}")
        if 'session' in locals() and session:
            session.close()
    
    try:
        context.bot.delete_message(chat_id=user_id, message_id=message_id)
        logger.info(f"[SURVEY_GENDER] Успешно удалено сообщение с клавиатурой пола для пользователя {user_id}")
    except Exception as e:
        logger.error(f"[SURVEY_GENDER_ERROR] Ошибка при удалении сообщения с клавиатурой: {e}")
    
    try:
        image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'img', '2_VOZRAST.jpg')
        
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                sent_message = context.bot.send_photo(
                    chat_id=user_id,
                    photo=photo,
                    caption="Отлично! Теперь укажи свой возраст (просто напиши число):"
                )
        else:
            sent_message = context.bot.send_message(
                chat_id=user_id,
                text="Отлично! Теперь укажи свой возраст (просто напиши число):"
            )
        
        context.user_data['bot_messages'] = [sent_message.message_id]
        logger.info(f"[SURVEY_AGE_REQUEST] Отправлен запрос возраста пользователю {user_id}, message_id: {sent_message.message_id}")
    except Exception as e:
        logger.error(f"[SURVEY_ERROR] Критическая ошибка при отправке вопроса о возрасте: {e}")
        try:
            context.bot.send_message(
                chat_id=user_id,
                text="Укажи свой возраст (число):"
            )
        except:
            logger.error(f"[SURVEY_ERROR] Невозможно продолжить опрос для пользователя {user_id}")
            return ConversationHandler.END
    
    logger.info(f"[SURVEY_TRANSITION] Переходим к шагу AGE для пользователя {user_id}")
    return AGE

def age(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    logger.info(f"[SURVEY_AGE] Получен ответ от пользователя {user_id}: {update.message.text}")
    
    try:
        user_age = int(update.message.text.strip())
        
        if user_age < 10 or user_age > 100:
            update.message.reply_text("Пожалуйста, введи реальный возраст от 10 до 100 лет:")
            logger.warning(f"[SURVEY_AGE] Пользователь {user_id} ввел некорректный возраст: {user_age}")
            return AGE
            
        context.user_data['age'] = user_age
        logger.info(f"[SURVEY_AGE] Пользователь {user_id} указал возраст: {user_age}")
        
        user_message_id = update.message.message_id
        
        try:
            session = get_session()
            user = session.query(User).filter(User.user_id == user_id).first()
            if user:
                user.age = user_age
                session.commit()
                logger.info(f"[SURVEY_AGE] Возраст пользователя {user_id} сохранен в БД")
            session.close()
        except Exception as e:
            logger.error(f"[SURVEY_AGE_ERROR] Ошибка при сохранении возраста в БД: {e}")
            if 'session' in locals() and session:
                session.close()
        
        if 'bot_messages' in context.user_data:
            for msg_id in context.user_data['bot_messages']:
                try:
                    context.bot.delete_message(
                        chat_id=update.message.chat_id,
                        message_id=msg_id
                    )
                except Exception as e:
                    logger.error(f"[SURVEY_ERROR] Ошибка при удалении сообщения бота: {e}")
        
        image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'img', '3_ROST.jpg')
        
        try:
            context.bot.delete_message(
                chat_id=update.message.chat_id,
                message_id=user_message_id
            )
        except Exception as e:
            logger.error(f"[SURVEY_ERROR] Ошибка при удалении сообщения пользователя: {e}")
        
        context.user_data['bot_messages'] = []
        
        try:
            if os.path.exists(image_path):
                with open(image_path, 'rb') as photo:
                    bot_message = context.bot.send_photo(
                        chat_id=user_id,
                        photo=photo,
                        caption="Спасибо! Теперь укажи свой рост\nв сантиметрах (просто напиши число):"
                    )
                    
                    context.user_data['bot_messages'].append(bot_message.message_id)
            else:
                logger.warning(f"[SURVEY_ERROR] Файл изображения не найден: {image_path}")
                bot_message = context.bot.send_message(
                    chat_id=user_id,
                    text="Спасибо! Теперь укажи свой рост\nв сантиметрах (просто напиши число):"
                )
                
                context.user_data['bot_messages'].append(bot_message.message_id)
        except Exception as e:
            logger.error(f"[SURVEY_ERROR] Ошибка при отправке запроса о росте: {e}")
            bot_message = context.bot.send_message(
                chat_id=user_id,
                text="Спасибо! Теперь укажи свой рост\nв сантиметрах (просто напиши число):"
            )
        
        logger.info(f"[SURVEY_TRANSITION] Переходим к шагу HEIGHT для пользователя {user_id}")
        return HEIGHT
    except ValueError:
        logger.warning(f"[SURVEY_AGE_ERROR] Пользователь {user_id} ввел некорректное значение: {update.message.text}")
        update.message.reply_text("Пожалуйста, введи возраст\nв виде числа (например, 30):")
        return AGE
    except Exception as e:
        logger.error(f"[SURVEY_AGE_ERROR] Непредвиденная ошибка: {e}")
        update.message.reply_text("Произошла ошибка. Пожалуйста, введи свой возраст еще раз:")
        return AGE

def height(update: Update, context: CallbackContext) -> int:
    try:
        user_height = int(update.message.text)
        user_id = update.effective_user.id
        context.user_data['height'] = user_height
        
        user_message_id = update.message.message_id
        
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        if user:
            user.height = user_height
            session.commit()
        session.close()
        
        if 'bot_messages' in context.user_data:
            for msg_id in context.user_data['bot_messages']:
                try:
                    context.bot.delete_message(
                        chat_id=update.message.chat_id,
                        message_id=msg_id
                    )
                except Exception as e:
                    logger.error(f"Ошибка при удалении сообщения бота: {e}")
        
        image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'img', '4_VES.jpg')
        
        try:
            context.bot.delete_message(
                chat_id=update.message.chat_id,
                message_id=user_message_id
            )
        except Exception as e:
            logger.warning(f"[SURVEY_ERROR] Не удалось удалить сообщение пользователя: {e}")
        
        context.user_data['bot_messages'] = []
        
        try:
            with open(image_path, 'rb') as photo:
                bot_message = context.bot.send_photo(
                    chat_id=user_id,
                    photo=photo,
                    caption="Теперь укажи свой вес\nв килограммах (просто напиши число):"
                )
                
                context.user_data['bot_messages'].append(bot_message.message_id)
        except Exception as e:
            logger.warning(f"[SURVEY_ERROR] Ошибка при отправке изображения: {e}")
            bot_message = context.bot.send_message(
                chat_id=user_id,
                text="Теперь укажи свой вес\nв килограммах (просто напиши число):"
            )
            context.user_data['bot_messages'].append(bot_message.message_id)
        
        return WEIGHT
    except ValueError:
        update.message.reply_text("Пожалуйста, введи рост\nв виде числа (например, 175):")
        return HEIGHT

def weight(update: Update, context: CallbackContext) -> int:
    try:
        user_weight = int(update.message.text)
        user_id = update.effective_user.id
        context.user_data['weight'] = user_weight
        
        user_message_id = update.message.message_id
        
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        if user:
            user.weight = user_weight
            session.commit()
        session.close()
        
        if 'bot_messages' in context.user_data:
            for msg_id in context.user_data['bot_messages']:
                try:
                    context.bot.delete_message(
                        chat_id=update.message.chat_id,
                        message_id=msg_id
                    )
                except Exception as e:
                    logger.error(f"Ошибка при удалении сообщения бота: {e}")
        
        context.user_data['selected_goals'] = []
        
        image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'img', '5_OSNOVNAYA.jpg')
        
        try:
            context.bot.delete_message(
                chat_id=update.message.chat_id,
                message_id=user_message_id
            )
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщения пользователя: {e}")
        
        context.user_data['bot_messages'] = []
        
        try:
            with open(image_path, 'rb') as photo:
                bot_message = context.bot.send_photo(
                    chat_id=user_id,
                    photo=photo,
                    caption="Какая твоя основная цель?\n(выбери свой вариант, можно выбрать несколько из списка):",
                    reply_markup=main_goal_keyboard()
                )
                context.user_data['bot_messages'].append(bot_message.message_id)
        except Exception as e:
            logger.error(f"Ошибка при отправке фото: {e}")
            bot_message = context.bot.send_message(
                chat_id=user_id,
                text="Какая твоя основная цель?\n(выбери свой вариант, можно выбрать несколько из списка):",
                reply_markup=main_goal_keyboard()
            )
            context.user_data['bot_messages'].append(bot_message.message_id)
        
        return MAIN_GOAL
    except ValueError:
        update.message.reply_text("Пожалуйста, введи вес\nв виде числа (например, 70):")
        return WEIGHT

def main_goal(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    user_id = update.effective_user.id
    
    goal_dict = {
        'goal_1': 'Снижение веса',
        'goal_2': 'Набор мышечной массы',
        'goal_3': 'Коррекция осанки',
        'goal_4': 'Убрать зажатость в теле',
        'goal_5': 'Общий тонус/рельеф мышц',
        'goal_6': 'Восстановиться после родов',
        'goal_7': 'Снять эмоциональное напряжение',
        'goal_8': 'Улучшить качество сна',
        'goal_9': 'Стать более энергичным'
    }
    
    if query.data == 'goals_done':
        if not context.user_data.get('selected_goals'):
            query.answer("Выберите хотя бы одну цель!")
            return MAIN_GOAL
        
        selected_goals_text = ", ".join(context.user_data['selected_goals'])
        context.user_data['main_goal'] = selected_goals_text
        
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        if user:
            user.main_goal = selected_goals_text
            session.commit()
        session.close()
        
        try:
            context.bot.delete_message(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id
            )
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщения: {e}")
        
        if 'bot_messages' not in context.user_data:
            context.user_data['bot_messages'] = []
        
        bot_message = context.bot.send_message(
            chat_id=user_id,
            text=f"Вы выбрали цели: {selected_goals_text}\n\nКакая дополнительная цель?",
            reply_markup=additional_goal_keyboard()
        )
        context.user_data['bot_messages'].append(bot_message.message_id)
        
        return ADDITIONAL_GOAL
    
    goal_key = query.data
    if goal_key in goal_dict:
        goal_name = goal_dict[goal_key]
        
        if 'selected_goals' not in context.user_data:
            context.user_data['selected_goals'] = []
            
        if goal_name not in context.user_data['selected_goals']:
            context.user_data['selected_goals'].append(goal_name)
        else:
            context.user_data['selected_goals'].remove(goal_name)
        
        selected_goals = context.user_data['selected_goals']
        goals_text = "Текущие выбранные цели:\n" + "\n".join([f"• {goal}" for goal in selected_goals]) if selected_goals else "Цели пока не выбраны"
        
        keyboard = []
        for g_key, g_name in goal_dict.items():
            prefix = "✅" if g_name in selected_goals else "☑️"
            keyboard.append([InlineKeyboardButton(f"{prefix} {g_name}", callback_data=g_key)])
        
        keyboard.append([InlineKeyboardButton("Готово ✓", callback_data="goals_done")])
        
        try:
            current_caption = query.message.caption or ""
            
            context.bot.edit_message_caption(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                caption=f"{goals_text}\n\nВыберите ваши цели\n(можно несколько):",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            logger.info(f"Обновлено сообщение с выбором целей для пользователя {user_id}")
        except Exception as e:
            logger.error(f"Ошибка при обновлении сообщения с выбором целей: {e}")
        
        return MAIN_GOAL
    
    return MAIN_GOAL

def additional_goal(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    logger.info(f"Обработка выбора дополнительной цели для пользователя {user_id}, выбор: {query.data}")
    
    goal_dict = {
        'add_goal_1': 'Послушать лекции от врачей, тренеров',
        'add_goal_2': 'Послушать лекции от проф психологов',
        'add_goal_3': 'Больше узнать о здоровом питании',
        'add_goal_4': 'Добавить в свою жизнь медитации, практики',
        'add_goal_5': 'Обрести новые знакомства',
        'add_goal_6': 'Поддержка, обратная связь, мотивация'
    }
    
    if query.data == 'additional_goals_done':
        if not context.user_data.get('selected_additional_goals'):
            query.answer("Выберите хотя бы одну дополнительную цель!")
            return ADDITIONAL_GOAL
        
        selected_goals_text = ", ".join(context.user_data['selected_additional_goals'])
        context.user_data['additional_goal'] = selected_goals_text
        
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        if user:
            user.additional_goal = selected_goals_text
            session.commit()
        session.close()
        
        try:
            context.bot.delete_message(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id
            )
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщения: {e}")
        
        if 'bot_messages' not in context.user_data:
            context.user_data['bot_messages'] = []
        
        image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'img', '7_FORMAT.jpg')
        
        try:
            with open(image_path, 'rb') as photo:
                bot_message = context.bot.send_photo(
                    chat_id=user_id,
                    photo=photo,
                    caption=f"Вы выбрали дополнительные цели: {selected_goals_text}\n\nКакой у вас формат работы?",
                    reply_markup=work_format_keyboard()
                )
                context.user_data['bot_messages'].append(bot_message.message_id)
        except Exception as e:
            logger.error(f"Ошибка при отправке фото: {e}")
            bot_message = context.bot.send_message(
                chat_id=user_id,
                text=f"Вы выбрали дополнительные цели: {selected_goals_text}\n\nКакой у вас формат работы?",
                reply_markup=work_format_keyboard()
            )
            context.user_data['bot_messages'].append(bot_message.message_id)
        
        return WORK_FORMAT
    
    goal_key = query.data
    if goal_key in goal_dict:
        goal_name = goal_dict[goal_key]
        logger.info(f"Выбрана дополнительная цель: {goal_name}")
        
        if 'selected_additional_goals' not in context.user_data:
            context.user_data['selected_additional_goals'] = []
            
        if goal_name not in context.user_data['selected_additional_goals']:
            context.user_data['selected_additional_goals'].append(goal_name)
        else:
            context.user_data['selected_additional_goals'].remove(goal_name)
        
        selected_goals = context.user_data['selected_additional_goals']
        goals_text = "Текущие выбранные дополнительные цели:\n" + "\n".join([f"• {goal}" for goal in selected_goals]) if selected_goals else "Дополнительные цели пока не выбраны"
        
        keyboard = []
        for g_key, g_name in goal_dict.items():
            prefix = "✅" if g_name in selected_goals else "☑️"
            keyboard.append([InlineKeyboardButton(f"{prefix} {g_name}", callback_data=g_key)])
        
        keyboard.append([InlineKeyboardButton("Готово ✓", callback_data="additional_goals_done")])
        
        try:
            context.bot.edit_message_text(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                text=f"{goals_text}\n\nВыберите дополнительные цели\n(можно несколько):",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            logger.info(f"Обновлено сообщение с выбором дополнительных целей для пользователя {user_id}")
        except Exception as e:
            logger.error(f"Ошибка при обновлении сообщения с выбором дополнительных целей: {e}")
        
        return ADDITIONAL_GOAL
    
    logger.warning(f"Получен неизвестный callback_data для дополнительной цели: {query.data}")
    return ADDITIONAL_GOAL

def work_format(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    user_work_format = query.data
    context.user_data['work_format'] = user_work_format
    
    session = get_session()
    user = session.query(User).filter(User.user_id == user_id).first()
    if user:
        user.work_format = user_work_format
        session.commit()
    session.close()
    
    if 'bot_messages' in context.user_data:
        for msg_id in context.user_data['bot_messages']:
            try:
                context.bot.delete_message(
                    chat_id=query.message.chat_id,
                    message_id=msg_id
                )
            except Exception as e:
                logger.error(f"Ошибка при удалении сообщения бота: {e}")
    
    image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'img', '8_SKOLKO.jpg')
    
    try:
        context.bot.delete_message(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id
        )
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения: {e}")
    
    context.user_data['bot_messages'] = []
    
    try:
        with open(image_path, 'rb') as photo:
            bot_message = context.bot.send_photo(
                chat_id=user_id,
                photo=photo,
                caption="Как часто занимаешься спортом?",
                reply_markup=sport_frequency_keyboard()
            )
            context.user_data['bot_messages'].append(bot_message.message_id)
    except Exception as e:
        logger.error(f"Ошибка при отправке фото: {e}")
        bot_message = context.bot.send_message(
            chat_id=user_id,
            text="Как часто занимаешься спортом?",
            reply_markup=sport_frequency_keyboard()
        )
        context.user_data['bot_messages'].append(bot_message.message_id)
    
    return SPORT_FREQUENCY

def sport_frequency(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    user_sport_frequency = query.data
    context.user_data['sport_frequency'] = user_sport_frequency
    
    session = get_session()
    user = session.query(User).filter(User.user_id == user_id).first()
    if user:
        user.sport_frequency = user_sport_frequency
        user.registered = True  # Отмечаем, что основная регистрация завершена
        session.commit()
    session.close()
    
    is_subscribed, paid_till = check_subscription_status(user_id)
    
    if 'bot_messages' in context.user_data:
        for msg_id in context.user_data['bot_messages']:
            try:
                context.bot.delete_message(
                    chat_id=query.message.chat_id,
                    message_id=msg_id
                )
            except Exception as e:
                logger.error(f"Ошибка при удалении сообщения бота: {e}")
    
    try:
        context.bot.delete_message(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id
        )
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения: {e}")
    
    context.user_data['bot_messages'] = []
    
    image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'img', 'SPASIBO_ZA_OTVETI.png')
    
    if is_subscribed:
        try:
            with open(image_path, 'rb') as photo:
                bot_message = context.bot.send_photo(
                    chat_id=user_id,
                    photo=photo,
                    caption="Спасибо за предоставленную информацию! 👍\n\n"
                            "У вас уже есть активная подписка. Доступ к сервису открыт!"
                )
                context.user_data['bot_messages'].append(bot_message.message_id)
            context.bot.send_message(
                chat_id=user_id,
                text="Рад видеть вас снова! Выберите действие из меню:",
                reply_markup=get_main_keyboard()
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке фото: {e}")
            bot_message = context.bot.send_message(
                chat_id=user_id,
                text="Спасибо за предоставленную информацию! 👍\n\n"
                    "У вас уже есть активная подписка. Доступ к сервису открыт!",
                reply_markup=get_main_keyboard()
            )
            context.user_data['bot_messages'].append(bot_message.message_id)
    else:
        selected_goals = context.user_data.get('selected_goals', [])
        goals_text = ", ".join(selected_goals).lower() if selected_goals else "достижение твоих целей"
        
        try:
            with open(image_path, 'rb') as photo:
                bot_message = context.bot.send_photo(
                    chat_id=user_id,
                    photo=photo,
                    caption=(f"Спасибо за твои ответы! Для того, чтобы ты смог прийти к своей цели:\n" +
                            (f"- " + "\n- ".join(selected_goals) + "\n\n" if selected_goals else "") +
                            f"Для тебя готова программа, которая будет доступна сразу после оплаты подписки\n\n"
                            f"*Так же health-ассистент подберет для тебя:* \n\n"
                            f"- программу питания\n"
                            f"- Сделает разбор анализов на наличие дефицитов в организме,\n"
                            f"чтобы ты смог комплексно подойти к своему здоровью"),
                    reply_markup=get_payment_keyboard(user_id, context),
                    parse_mode=ParseMode.MARKDOWN
                )
                context.user_data['bot_messages'].append(bot_message.message_id)
        except Exception as e:
            logger.error(f"Ошибка при отправке фото: {e}")
            bot_message = context.bot.send_message(
                chat_id=user_id,
                text=(f"Спасибо за твои ответы! Для того, чтобы ты смог прийти к своей цели:\n" +
                    (f"- " + "\n- ".join(selected_goals) + "\n\n" if selected_goals else "") +
                    f"Для тебя готова программа, которая будет доступна сразу после оплаты подписки\n\n"
                    f"*Так же health-ассистент подберет для тебя:* \n\n"
                     f"- программу питания\n"
                     f"- Сделает разбор анализов на наличие дефицитов в организме,\n"
                    f"чтобы ты смог комплексно подойти к своему здоровью"),
                reply_markup=get_payment_keyboard(user_id, context),
                parse_mode=ParseMode.MARKDOWN
            )
            # Сохраняем ID сообщения бота
            context.user_data['bot_messages'].append(bot_message.message_id)
    
    return ConversationHandler.END


def payment(update: Update, context: CallbackContext) -> int:
    """
    Функция для отображения вариантов подписки
    """
    user_id = update.effective_user.id
    
    # Получаем клавиатуру с вариантами подписки из модуля с обработкой сомнений
    from bot.subscription_doubt_handler import get_subscription_keyboard
    
    update.message.reply_text(
        "Варианты WILLWAY подписки:",
        reply_markup=get_subscription_keyboard()
    )
    return ConversationHandler.END

def handle_menu_callback(update: Update, context: CallbackContext):
    """
    Обработчик нажатий на кнопки инлайн клавиатуры.
    """
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    callback_data = query.data
    
    logger.info(f"[CALLBACK] Пользователь {user_id} нажал на кнопку: {callback_data}")
    
    # Проверка подписки для функций, требующих активной подписки
    if callback_data == "health_assistant":
        # Проверяем подписку
        is_subscribed = update_subscription_status(user_id, context)
        
        if not is_subscribed:
            query.edit_message_text(
                "Для доступа к Health ассистенту необходимо оформить подписку.",
                reply_markup=get_payment_keyboard_inline(user_id)
            )
            return
        
        # Если подписка активна, отправляем приветствие Health ассистента
        query.edit_message_text(
            "Привет! Я твой личный health-ассистент WILLWAY. Помогу тебе создать здоровое подтянутое тело, улучшить ментальное состояние и внедрить новые привычки, которые реально улучшают качество жизни.\n\n"
            "Я здесь, чтобы поддерживать тебя на пути, не давая сбиться с курса, мотивировать и подсказывать, что делать на каждом этапе.\n\n"
            "Скажи с чего начнем: \n"
            "- Программа тренировок \n"
            "- Программа питания/разбор анализов \n"
            "- Программа восстановления ментального состояния.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_to_menu")]])
        )
        
        # Отправляем дополнительное сообщение с клавиатурой для отправки вопросов
        context.bot.send_message(
            chat_id=user_id,
            text="Задай мне вопрос о здоровье, питании или тренировках:",
            reply_markup=ReplyKeyboardMarkup([["Назад"]], resize_keyboard=True)
        )
        
        return

    # Обработка кнопки "Управление подпиской"
    elif callback_data == "subscription_management":
        # Получаем данные о подписке пользователя
        try:
            session = get_session()
            user = session.query(User).filter(User.user_id == user_id).first()
            
            if user:
                is_subscribed = user.is_subscribed
                subscription_type = user.subscription_type
                subscription_expires = user.subscription_expires
                
                if is_subscribed and subscription_expires:
                    # Форматируем дату окончания подписки
                    expires_date = subscription_expires.strftime("%d.%m.%Y")
                    remaining_days = (subscription_expires - datetime.now()).days
                    
                    # Определяем тип подписки для отображения
                    sub_type = "месячная" if subscription_type == "monthly" else "годовая"
                    
                    # Получаем username менеджера из конфигурации
                    config = get_bot_config()
                    manager_username = config.get("manager_username", "willway_manager")
                    
                    # Создаем клавиатуру для управления подпиской
                    keyboard = [
                        [InlineKeyboardButton("Продлить подписку", callback_data="renew_subscription")],
                        [get_cancel_subscription_button()]
                    ]
                    
                    # Отправляем информацию о подписке
                    query.edit_message_text(
                        f"💎 *Информация о подписке*\n\n"
                        f"• Тип: {sub_type}\n"
                        f"• Активна до: {expires_date}\n"
                        f"• Осталось дней: {remaining_days}\n\n"
                        f"Для отмены подписки нажмите соответствующую кнопку ниже.",
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    # Если подписка не активна
                    query.edit_message_text(
                        "У вас нет активной подписки.\n\n"
                        "Оформите подписку для доступа к Health ассистенту и другим функциям бота:",
                        reply_markup=get_payment_keyboard_inline(user_id)
                    )
            else:
                # Если данные о пользователе не найдены
                query.edit_message_text(
                    "Не удалось получить информацию о вашей подписке. Пожалуйста, попробуйте позже.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_to_menu")]])
                )
        except Exception as e:
            logger.error(f"Ошибка при получении информации о подписке: {e}")
            query.edit_message_text(
                "Произошла ошибка при загрузке информации о подписке. Пожалуйста, попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_to_menu")]])
            )
        finally:
            if 'session' in locals() and session:
                session.close()
        return

    # Обработка кнопки "Связь с поддержкой"
    elif callback_data == "support":
        # Показываем кнопки для связи с менеджером и тренером
        query.edit_message_text(
            "Выберите с кем хотите связаться:",
            reply_markup=support_keyboard()
        )
        return

    # Обработка кнопки "Пригласить друга" (заглушка)
    elif callback_data == "invite_friend":
        # Получаем реферальный код пользователя из БД и показываем полную информацию
        session = get_session()
        try:
            # Проверяем, есть ли у пользователя реферальный код
            ref_code = session.query(ReferralCode).filter(
                ReferralCode.user_id == user_id, 
                ReferralCode.is_active == True
            ).first()
            
            if not ref_code:
                # Если кода нет, генерируем новый
                import random
                import string
                new_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                
                ref_code = ReferralCode(
                    user_id=user_id,
                    code=new_code,
                    is_active=True
                )
                session.add(ref_code)
                session.commit()
                
                code = new_code
                logger.info(f"[REFERRAL] Создан новый реферальный код {code} для пользователя {user_id}")
            else:
                code = ref_code.code
                logger.info(f"[REFERRAL] Найден существующий реферальный код {code} для пользователя {user_id}")
            
            # Получаем ID пользователя в базе данных
            user_db = session.query(User).filter(User.user_id == user_id).first()
            if not user_db:
                logger.error(f"[REFERRAL_ERROR] Пользователь с ID {user_id} не найден в БД")
                raise Exception("Пользователь не найден в базе данных")
                
            # Получаем количество приглашенных друзей
            total_invited = 0
            paid_friends = 0
            
            # Попытка 1: По полю referrer_id == user_id (telegram ID)
            try:
                total_invited = session.query(ReferralUse).filter(
                    ReferralUse.referrer_id == user_id
                ).count()
                
                paid_friends = session.query(ReferralUse).filter(
                    ReferralUse.referrer_id == user_id,
                    ReferralUse.subscription_purchased == True
                ).count()
                
                logger.info(f"[REFERRAL] Статистика по Telegram ID: всего={total_invited}, с подпиской={paid_friends}")
            except Exception as e:
                logger.warning(f"[REFERRAL_WARNING] Ошибка при получении статистики по Telegram ID: {str(e)}")
            
            # Если не нашли по прямому ID, пробуем через ID в БД
            if total_invited == 0:
                try:
                    total_invited = session.query(ReferralUse).filter(
                        ReferralUse.referrer_id == user_db.id
                    ).count()
                    
                    paid_friends = session.query(ReferralUse).filter(
                        ReferralUse.referrer_id == user_db.id,
                        ReferralUse.subscription_purchased == True
                    ).count()
                    
                    logger.info(f"[REFERRAL] Статистика по ID в БД: всего={total_invited}, с подпиской={paid_friends}")
                except Exception as e:
                    logger.warning(f"[REFERRAL_WARNING] Ошибка при получении статистики по ID в БД: {str(e)}")
            
            # Получаем имя бота
            bot_username = os.environ.get('TELEGRAM_BOT_USERNAME', 'willwayapp_bot')  # Получаем из переменной окружения
            try:
                bot_info = context.bot.get_me()
                bot_username = bot_info.username
            except:
                logger.error("Не удалось получить username бота")
            
            # Формируем реферальную ссылку
            referral_link = f"https://t.me/{bot_username}?start={code}"
            
            # Получаем клавиатуру и ссылку
            keyboard, referral_link = get_referral_keyboard(user_id, code)
            
            # Формируем простое сообщение без эмодзи и сложного форматирования, но с ссылкой
            message = (
                "Приглашайте друзей и получайте бонусы!\n\n"
                "За каждого друга, который оформит подписку, "
                "вы получите +1 месяц к вашей текущей подписке.\n\n"
                "Статистика:\n"
                f"- Всего приглашено друзей: {total_invited}\n"
                f"- Друзей с подпиской: {paid_friends}\n"
                f"- Бонусных месяцев получено: {paid_friends}\n\n"
                f"Ваша реферальная ссылка: {referral_link}\n\n"
                f"Ваш реферальный код: {code}"
            )
            
            # Создаем клавиатуру
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Назад", callback_data="back_to_menu")]
            ])
            
            # Отправляем сообщение
            context.bot.send_message(
                chat_id=user_id,
                text=message,
                reply_markup=keyboard
            )
            
        except Exception as e:
            logger.error(f"[REFERRAL_ERROR] Ошибка при обработке приглашения друга: {str(e)}")
            context.bot.send_message(
                chat_id=user_id,
                text="Произошла ошибка при получении вашей реферальной ссылки. Пожалуйста, попробуйте позже."
            )
        finally:
            session.close()
        return
        
    # Обработка кнопок реферальной системы
    elif callback_data.startswith("copy_ref_link_"):
        # Получаем код из callback_data
        ref_code = callback_data.replace("copy_ref_link_", "")
        
        try:
            # Получаем имя бота
            bot_username = os.environ.get('TELEGRAM_BOT_USERNAME', 'willwayapp_bot')  # Получаем из переменной окружения
            try:
                bot_info = context.bot.get_me()
                bot_username = bot_info.username
            except:
                logger.error("Не удалось получить username бота")
            
            # Формируем реферальную ссылку
            referral_link = f"https://t.me/{bot_username}?start={ref_code}"
            
            # Отправляем ссылку в отдельном сообщении, чтобы пользователь мог скопировать ее
            context.bot.send_message(
                chat_id=user_id,
                text=f"Ваша реферальная ссылка:\n{referral_link}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Вернуться к реферальной программе", callback_data="invite_friend")
                ]])
            )
            
            # Даем знать пользователю, что ссылка была отправлена
            query.answer("Ссылка отправлена в сообщении!")
        except Exception as e:
            logger.error(f"[REFERRAL_ERROR] Ошибка при копировании реферальной ссылки: {str(e)}")
        query.edit_message_text(
                "Произошла ошибка при копировании ссылки. Пожалуйста, попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="invite_friend")]])
        )
        return
        
    elif callback_data == "referral_stats":
        session = get_session()
        try:
            # Получаем список приглашенных пользователей
            referrals = session.query(ReferralUse, User).join(
                User, ReferralUse.referred_id == User.user_id
            ).filter(
                ReferralUse.referrer_id == user_id
            ).all()
            
            if not referrals:
                query.edit_message_text(
                    "У вас пока нет приглашенных друзей. Поделитесь своей реферальной ссылкой с друзьями, чтобы получать бонусы!",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="invite_friend")]])
                )
                return
            
            # Формируем сообщение со статистикой
            message = "📊 *Статистика ваших приглашений:*\n\n"
            
            for i, (ref_use, user) in enumerate(referrals, 1):
                username = user.username or "Пользователь"
                status = "✅ Оформил подписку" if ref_use.subscription_purchased else "❌ Без подписки"
                date = ref_use.used_at.strftime("%d.%m.%Y")
                
                message += f"{i}. *{username}* - {status}\n"
                message += f"   Дата регистрации: {date}\n"
                
                if ref_use.subscription_purchased:
                    purchase_date = ref_use.purchase_date.strftime("%d.%m.%Y") if ref_use.purchase_date else "Неизвестно"
                    message += f"   Дата оплаты: {purchase_date}\n"
                
                message += "\n"
            
            # Добавляем общую статистику
            total_invited = len(referrals)
            paid_friends = sum(1 for ref, _ in referrals if ref.subscription_purchased)
            
            message += f"*Всего приглашено:* {total_invited}\n"
            message += f"*С подпиской:* {paid_friends}\n"
            message += f"*Бонусных месяцев получено:* {paid_friends}"
            
            query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="invite_friend")]])
            )
        except Exception as e:
            logger.error(f"[REFERRAL_ERROR] Ошибка при отображении статистики рефералов: {str(e)}")
            query.edit_message_text(
                "Произошла ошибка при получении статистики приглашений. Пожалуйста, попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="invite_friend")]])
            )
        finally:
            session.close()
        return

    # Обработка кнопки "Назад в меню"
    elif callback_data == "back_to_menu":
        logger.info(f"[MENU] Пользователь {user_id} нажал кнопку 'Назад', возвращаемся в главное меню")
        # Вызываем функцию возврата в главное меню
        return back_to_main_menu(update, context)
        
    # Обработка кнопок подписки
    # Обработка кнопок для оплаты
    elif callback_data == "payment_monthly" or callback_data == "payment_yearly":
        subscription_type = "monthly" if callback_data == "payment_monthly" else "yearly"
        logger.info(f"[PAYMENT_SELECTED] Пользователь {user_id} выбрал {subscription_type} подписку")
        
        # Получаем данные пользователя из БД
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        session.close()
        
        # Собираем данные пользователя для платежа
        user_data = {
            'user_id': user_id,
            'email': user.email if user and user.email else None,
            'phone': user.phone if user and user.phone else None,
            'username': update.effective_user.username
        }
        
        # Инициализируем обработчик платежей
        payment_handler = PaymentHandler()
        
        # Создаем ссылку на оплату на Tilda
        payment_url = payment_handler.generate_tilda_payment_link(user_data, subscription_type)
        
        # Проверяем, что ссылка успешно создана
        if payment_url:
            # Отправляем сообщение с ссылкой на оплату
            query.edit_message_text(
                text=f"Для оплаты {'месячной' if subscription_type == 'monthly' else 'годовой'} подписки нажмите на кнопку ниже.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Перейти к оплате", url=payment_url)],
                    [InlineKeyboardButton("Отменить", callback_data="cancel_payment")]
                ])
            )
            
            # Логируем событие создания ссылки на оплату
            logger.info(f"[PAYMENT_LINK_CREATED] Для пользователя {user_id} создана ссылка на оплату: {payment_url}")
            
            # Устанавливаем напоминание о незавершенной оплате
            schedule_payment_reminder(context, user_id, delay_minutes=30)
        else:
            # Если не удалось создать ссылку, показываем сообщение об ошибке
            query.edit_message_text(
                text="Извините, в данный момент система оплаты недоступна. Пожалуйста, попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Вернуться в меню", callback_data="back_to_menu")]
                ])
            )
            logger.error(f"[PAYMENT_ERROR] Не удалось создать ссылку на оплату для пользователя {user_id} (тип: {subscription_type})")
        
        return
    
    # Обработка отмены платежа
    elif callback_data == "cancel_payment":
        logger.info(f"[PAYMENT_CANCELLED] Пользователь {user_id} отменил платеж")
        
        # Отменяем запланированное напоминание о платеже
        cancel_payment_reminder(context, user_id)
        
        # Возвращаемся в главное меню
        query.edit_message_text(
            text="Оплата отменена. Вы можете вернуться в главное меню.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Вернуться в меню", callback_data="back_to_menu")]
            ])
        )
        
        return
    
    # Обработка кнопки продления подписки
    elif callback_data == "renew_subscription":
        # Создаем запись о платеже
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if user and user.subscription_type:
            subscription_type = user.subscription_type
            session.close()
            
            # Создаем ссылку на оплату соответствующего типа подписки
            payment_url = generate_payment_url(user_id, subscription_type)
            
            # Проверяем, что ссылка успешно создана
            if payment_url:
                keyboard = [[InlineKeyboardButton("Оплатить", url=payment_url)],
                            [InlineKeyboardButton("Вернуться в меню", callback_data="back_to_menu")]]
                
                # Определяем стоимость и период подписки
                if subscription_type == "monthly":
                    amount = f"{MONTHLY_SUBSCRIPTION_PRICE:,}".replace(",", " ") + " ₽"
                    period = "30 дней"
                else:  # yearly
                    amount = f"{YEARLY_SUBSCRIPTION_PRICE:,}".replace(",", " ") + " ₽"
                    period = "365 дней"
                
                query.edit_message_text(
                    text=(
                        f"💎 *Продление {subscription_type} подписки WILLWAY*\n\n"
                        f"• Стоимость: {amount}\n"
                        f"• Период: {period}\n\n"
                        f"Нажмите кнопку ниже, чтобы продлить подписку."
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                # Если не удалось создать ссылку на оплату
                query.edit_message_text(
                    text="Извините, в данный момент система оплаты недоступна. Пожалуйста, попробуйте позже.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Вернуться в меню", callback_data="back_to_menu")]
                    ])
                )
                logger.error(f"[PAYMENT_ERROR] Не удалось создать ссылку на продление подписки для пользователя {user_id} (тип: {subscription_type})")
        else:
            if session:
                session.close()
            
            # Если тип подписки неизвестен, предлагаем выбрать
            # Форматируем цены с разделителями тысяч и символом рубля
            monthly_price = f"{MONTHLY_SUBSCRIPTION_PRICE:,}".replace(",", " ") + " ₽"
            yearly_price = f"{YEARLY_SUBSCRIPTION_PRICE:,}".replace(",", " ") + " ₽"
            
            # Расчет процента экономии при годовой подписке
            monthly_yearly = MONTHLY_SUBSCRIPTION_PRICE * 12
            savings_percent = round((monthly_yearly - YEARLY_SUBSCRIPTION_PRICE) / monthly_yearly * 100)
            
            query.edit_message_text(
                text=(
                    "💎 *Подписка WILLWAY*\n\n"
                    "Выберите подходящий вам тариф:\n\n"
                    f"• *Месяц* - {monthly_price}\n"
                    f"• *Год* - {yearly_price} (экономия {savings_percent}%)\n\n"
                    "Подписка открывает доступ ко всем функциям бота."
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=payment_keyboard()
            )
    # Обработка кнопок подписки из нового модуля
    elif callback_data == "subscription_30days":
        # Обработка выбора месячной подписки
        logger.info(f"[PAYMENT_SELECTED] Пользователь {user_id} выбрал месячную подписку (30 дней)")
        
        # Генерируем URL оплаты и отправляем сообщение с ним
        payment_url = generate_payment_url(user_id, "monthly")
        if payment_url:
            keyboard = [[InlineKeyboardButton("Оплатить", url=payment_url)]]
            query.edit_message_text(
                text="Отлично! Вы выбрали месячную подписку (30 дней) за 1.555 руб.\n\nНажмите кнопку ниже, чтобы перейти к оплате.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            # Если не удалось создать ссылку, показываем сообщение об ошибке
            query.edit_message_text(
                text="Извините, в данный момент система оплаты недоступна. Пожалуйста, попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Вернуться в меню", callback_data="back_to_menu")]
                ])
            )
        return
    
    elif callback_data == "subscription_1year":
        # Обработка выбора годовой подписки
        logger.info(f"[PAYMENT_SELECTED] Пользователь {user_id} выбрал годовую подписку")
        
        # Генерируем URL оплаты и отправляем сообщение с ним
        payment_url = generate_payment_url(user_id, "yearly")
        if payment_url:
            keyboard = [[InlineKeyboardButton("Оплатить", url=payment_url)]]
            query.edit_message_text(
                text="Отлично! Вы выбрали годовую подписку за 13.333 руб. со скидкой 30% и доступом к тренеру.\n\nНажмите кнопку ниже, чтобы перейти к оплате.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            # Если не удалось создать ссылку, показываем сообщение об ошибке
            query.edit_message_text(
                text="Извините, в данный момент система оплаты недоступна. Пожалуйста, попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Вернуться в меню", callback_data="back_to_menu")]
                ])
            )
        return
    
    # Обработка кнопки запуска опроса
    elif callback_data == "start_survey":
        return start_survey(update, context)

    # Можно добавить дополнительные обработчики для других кнопок здесь

def generate_payment_url(user_id, subscription_type):
    """Генерирует URL для оплаты подписки"""
    logger.info(f"[PAYMENT] Генерация URL оплаты (пользователь {user_id}, тип {subscription_type})")
    # Формируем базовый URL страницы оплаты
    payment_url = "https://willway.pro/payment"
    # Добавляем только параметр ID пользователя
    full_url = f"{payment_url}?tgid={user_id}"
    logger.info(f"[PAYMENT] Сгенерирован URL: {full_url}")
    return full_url

def handle_payment_success(update: Update, context: CallbackContext, query=None) -> int:
    """Заглушка для обработки успешной оплаты (система оплаты отключена)"""
    user_id = update.effective_user.id if update else query.from_user.id
    logger.info(f"[PAYMENT_DISABLED] Попытка обработки успешной оплаты (пользователь {user_id})")
    return ConversationHandler.END

def send_successful_payment_messages(update: Update, context: CallbackContext, subscription_status):
    """Отправка сообщений об успешной оплате"""
    user_id = update.effective_user.id
    
    try:
        # Получаем данные о подписке пользователя
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if user:
            is_subscribed = user.is_subscribed
            subscription_type = user.subscription_type
            subscription_expires = user.subscription_expires
            
            if is_subscribed and subscription_expires:
                # Форматируем дату окончания подписки
                expires_date = subscription_expires.strftime("%d.%m.%Y")
                remaining_days = (subscription_expires - datetime.now()).days
                
                # Определяем тип подписки для отображения
                sub_type = "месячная" if subscription_type == "monthly" else "годовая"
                
                # Создаем клавиатуру для управления подпиской
                keyboard_subscription = InlineKeyboardMarkup([
                    [InlineKeyboardButton("Продлить подписку", callback_data="renew_subscription")],
                    [get_cancel_subscription_button()]
                ])
                
                # Отправляем информацию о подписке (точно как при нажатии кнопки "Управление подпиской")
                context.bot.send_message(
                    chat_id=user_id,
                    text=f"💎 *Информация о подписке*\n\n"
                         f"• Тип: {sub_type}\n"
                         f"• Активна до: {expires_date}\n"
                         f"• Осталось дней: {remaining_days}\n\n"
                         f"Для отмены подписки нажмите соответствующую кнопку ниже.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard_subscription
                )
    except Exception as e:
        logger.error(f"Ошибка при отправке информации о подписке: {str(e)}")
    
    # Затем отправляем основное сообщение об успешной оплате
    message = (
        "Спасибо за доверие. Ты сделал правильный выбор! "
        "Мы постараемся сделать все, чтобы помочь тебе прийти к своей цели.\n\n"
        "Давай введу тебя сразу в курс дела.\n\n"
        "По кнопкам внизу ты можешь:\n"
        "- получить доступ к приложению и личному кабинету, где тебя ждут твои программы,\n\n"
        "- добавиться в канал с анонсами мероприятий, прямых эфиров и просто "
        "полезной информацией о физическом и ментальном здоровье\n\n"
        "По кнопке menu ты можешь:\n"
        "- пообщаться с Health-ассистентом, подобрать программу питания, сделать разбор анализов\n"
        "- управлять своей подпиской,\n"
        "- связаться с поддержкой, задать вопрос тренеру/нутрициологу/психологу\n"
        "- пригласить в наш сервис друга и получить бонусы, которыми можно оплатить "
        "подписку или вывести себе на счет."
    )
    
    # Получаем URL канала из конфигурации
    config = get_bot_config()
    channel_url = config.get("channel_url", "https://t.me/willway_channel")
    
    # Создаем InlineKeyboard с кнопками
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(text="Доступ к приложению", web_app={"url": "https://willway.pro/"})],
        [InlineKeyboardButton(text="Вступить в канал", url=channel_url)]
    ])
    
    # Отправляем сообщение с InlineKeyboard
    context.bot.send_message(
        chat_id=user_id,
        text=message,
        reply_markup=keyboard
    )
    
    # Отправляем ReplyKeyboard кнопки
    try:
        reply_keyboard = get_main_keyboard()
        context.bot.send_message(
            chat_id=user_id,
            text="Меню доступно ниже ⬇️",
            reply_markup=reply_keyboard
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке ReplyKeyboard: {str(e)}")
        # Если не удалось получить клавиатуру из функции, создаем её вручную
        reply_keyboard = ReplyKeyboardMarkup([
            ["Health ассистент", "Управление подпиской"],
            ["Связь с поддержкой", "Пригласить друга"]
        ], resize_keyboard=True)
        context.bot.send_message(
            chat_id=user_id,
            text="Меню доступно ниже ⬇️",
            reply_markup=reply_keyboard
        )

def send_pending_message(user_id, manager_username):
    """Отправка сообщения о незавершенной оплате"""
    # Текст из скрина 3
    message = (
        "Мы видим, что ты начал(а) процесс оформления подписки, но не завершил оплату.\n\n"
        "Если у тебя возникли вопросы или нужна помощь с оплатой, просто напиши мне здесь "
        "и я с радостью помогу тебе"
    )
    
    # Создаем клавиатуру с кнопками
    keyboard = [
        [InlineKeyboardButton("Написать в поддержку", url=f"https://t.me/{manager_username}")],
        [InlineKeyboardButton("Посмотреть варианты подписки", url=f"https://willway.pro/payment?tgid={user_id}")]
    ]
    
    # Используем Bot для отправки сообщения
    bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
    
    # Отправляем сообщение с клавиатурой
    bot.send_message(
        chat_id=user_id,
        text=message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def send_payment_processing_messages(update: Update, context: CallbackContext):
    """Заглушка для отправки сообщений о обработке платежа (система оплаты отключена)"""
    user_id = update.effective_user.id
    logger.info(f"[PAYMENT_DISABLED] Попытка отправки сообщений о обработке платежа (пользователь {user_id})")
    return

def check_payment_status_job(context: CallbackContext):
    """Заглушка для проверки статуса платежа (система оплаты отключена)"""
    logger.info("[PAYMENT_DISABLED] Попытка проверки статуса платежа")
    return

def webhook_handler(update: Update, context: CallbackContext):
    """Заглушка для обработки webhook (система оплаты отключена)"""
    logger.info("[PAYMENT_DISABLED] Получен webhook (система оплаты отключена)")
    return

def create_payment_record(user_id, subscription_type, payment_amount, payment_status='pending'):
    """Заглушка для создания записи о платеже (система оплаты отключена)"""
    logger.info(f"[PAYMENT_DISABLED] Попытка создания записи о платеже (пользователь {user_id}, тип {subscription_type})")
    return False

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
    logger.info(f"[OTHER_MESSAGE] Получено необработанное сообщение от пользователя {user_id}: {text}")
    
    # Проверяем, является ли сообщение нажатием на кнопку "Подобрать персональную программу"
    if text == "Подобрать персональную программу":
        logger.info(f"[SURVEY_START] Пользователь {user_id} нажал на кнопку 'Подобрать персональную программу'")
        return start_survey(update, context)
    
    # Если это другое сообщение, отправляем сообщение о том, что команда не распознана
    update.message.reply_text(
        "Извините, я не понимаю эту команду. Пожалуйста, используйте меню для взаимодействия с ботом.",
        reply_markup=get_main_keyboard()
    )

def init_bot_configuration():
    """Инициализирует конфигурацию бота при запуске"""
    try:
        # Загружаем конфигурацию из файла
        config = get_bot_config()
        
        # Проверяем наличие необходимых полей в конфигурации
        if 'manager_username' not in config:
            config['manager_username'] = "willway_manager"
            logger.info("Добавлено значение по умолчанию для manager_username")
        
        if 'trainer_username' not in config:
            config['trainer_username'] = "willway_trainer"
            logger.info("Добавлено значение по умолчанию для trainer_username")
        
        # Обновляем описание команды help
        if 'commands' not in config:
            config['commands'] = {}
        
        config['commands']['/help'] = "Помощь"
        logger.info("Обновлено описание команды /help в конфигурации")
        
        # Сохраняем обновленную конфигурацию
        save_bot_config(config)
        
        logger.info("Конфигурация бота успешно инициализирована")
        return True
    except Exception as e:
        logger.error(f"Ошибка при инициализации конфигурации бота: {e}")
        return False

def initialize_bot():
    """
    Инициализирует и возвращает экземпляр бота Telegram
    """
    try:
        from telegram import Bot
        from dotenv import load_dotenv
        import os
        import logging
        
        # Настройка логирования
        logger = logging.getLogger(__name__)
        
        # Загружаем переменные окружения
        load_dotenv()
        
        # Получаем токен бота
        TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
        
        if not TELEGRAM_TOKEN:
            logger.error("Токен бота не найден в переменных окружения")
            return None
        
        # Инициализируем бота
        bot = Bot(token=TELEGRAM_TOKEN)
        logger.info("Бот успешно инициализирован")
        
        return bot
    except Exception as e:
        logger.error(f"Ошибка при инициализации бота: {str(e)}")
        return None

def main():
    """Основная функция запуска бота."""
    try:
        logger.info("[STARTUP] Запуск бота WILLWAY")
        
        # Инициализируем конфигурацию
        init_bot_configuration()
        
        # Получение токена
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            logger.error("Не указан TELEGRAM_TOKEN в переменных окружения!")
            return
        
        # Проверяем наличие прокси в переменных окружения
        proxy_url = os.getenv("TELEGRAM_PROXY_URL")
        
        # Создаем updater с прокси (если указан)
        if proxy_url:
            logger.info(f"Используется прокси: {proxy_url}")
            # Создаем реквест с прокси для telegram
            request = telegram.utils.request.Request(proxy_url=proxy_url)
            updater = Updater(token, request=request)
        else:
            # Обычное создание updater без прокси
            updater = Updater(token)
            
        dispatcher = updater.dispatcher
        
        # Настраиваем цветное логирование
        setup_colored_logging()
        
        # Читаем конфигурацию
        config = get_bot_config()
        
        # Настраиваем бота в соответствии с конфигурацией
        apply_bot_config(updater.bot, config)
        
        # Основной обработчик диалога
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler('start', start), 
                CommandHandler('survey', start_survey),
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
            fallbacks=[CommandHandler('cancel', cancel)],
            name="survey_conversation"
        )
        
        # Регистрируем обработчики
        dispatcher.add_handler(conv_handler)
        
        # Обработчики команд
        dispatcher.add_handler(CommandHandler("start", start))
        dispatcher.add_handler(CommandHandler("menu", show_menu))
        dispatcher.add_handler(CommandHandler("payment", payment))
        dispatcher.add_handler(CommandHandler("subscription", check_subscription))
        dispatcher.add_handler(CommandHandler("help", help_command))
        
        # Webhook для обработки платежей от CloudPayments
        dispatcher.add_handler(MessageHandler(Filters.regex(r'^webhook_payment:'), webhook_handler))
        
        # Обработчик для глубоких ссылок после успешной оплаты
        dispatcher.add_handler(CommandHandler("start", start))
        
        # Обработчики для работы с Health ассистентом
        dispatcher.add_handler(MessageHandler(Filters.regex(r'^Health ассистент$'), health_assistant_button))
        dispatcher.add_handler(MessageHandler(Filters.regex(r'^💬 Задать вопрос$'), health_assistant_button))
        
        # Обработчик для кнопки "Подобрать персональную программу"
        dispatcher.add_handler(MessageHandler(Filters.regex(r'^Подобрать персональную программу$'), start_survey))
        
        # Обработчики сообщений
        dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.chat_type.private & Filters.regex(r'^\/#/'), handle_health_assistant_message))
        dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.chat_type.private & Filters.regex(r'^support:/'), handle_support_messages))
        dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.chat_type.private, handle_text_messages))
        
        # Добавляем обработчики для схемы сомнений при выборе подписки
        setup_subscription_doubt_handlers(dispatcher)
        logger.info("Зарегистрированы обработчики для схемы сомнений при выборе подписки")
        
        # Добавляем обработчики для схемы отмены подписки
        setup_subscription_cancel_handlers(dispatcher)
        logger.info("Зарегистрированы обработчики для схемы отмены подписки")
        
        # Обработчик для кнопки "Варианты WILLWAY подписки"
        dispatcher.add_handler(CallbackQueryHandler(handle_show_subscription_options, pattern='^show_subscription_options$'))
        
        # Обработчик callback-запросов (общий - должен быть последним)
        dispatcher.add_handler(CallbackQueryHandler(handle_menu_callback))
        
        # Проверяем наличие переменных окружения для запуска в режиме webhook
        webhook_url = os.getenv("WEBHOOK_BASE_URL")
        token = os.getenv("TELEGRAM_TOKEN")
        
        # Запускаем бота
        if webhook_url:
            # Запуск в режиме webhook
            port = int(os.getenv("PORT", "8443"))
            logger.info(f"[STARTUP] Запуск бота в режиме webhook на {webhook_url}")
            updater.start_webhook(
                listen="0.0.0.0",
                port=port,
                url_path=token,
                webhook_url=f"{webhook_url}/{token}"
            )
        else:
            # Запуск в режиме polling (локальный режим)
            logger.info("[STARTUP] Запуск бота в режиме polling")
            
            # Дополнительная проверка и удаление webhook перед запуском polling
            try:
                # Удаляем webhook еще раз непосредственно перед запуском polling
                bot = updater.bot
                bot.delete_webhook(drop_pending_updates=True)
                logger.info("[STARTUP] Webhook удален непосредственно через API бота")
            except Exception as e:
                logger.error(f"[STARTUP] Ошибка при удалении webhook через API бота: {e}")
                
            updater.start_polling(drop_pending_updates=True)
        
        logger.info("[STARTUP] Бот запущен!")
        
        # Блокировка до прерывания работы
        updater.idle()
        
        # Запускаем ежедневную проверку истекающих подписок в 10:00 утра
        job_queue = updater.job_queue
        job_queue.run_daily(
            send_subscription_expiration_reminder,
            time=time(hour=10, minute=0, second=0),
            days=(0, 1, 2, 3, 4, 5, 6),
            context=None
        )
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        return

# Добавляем функцию для обработки datetime
def make_aware(dt):
    """Localize a naive datetime object to the configured timezone"""
    if dt and not dt.tzinfo:
        return TIMEZONE.localize(dt)
    return dt

def is_admin(user_id):
    """Проверяет, является ли пользователь администратором"""
    session = get_session()
    try:
        # В модели AdminUser нет поля user_id, поэтому используем другой подход
        # Проверяем, есть ли пользователь в специальном списке администраторов
        admin_usernames = ['admin', 'superadmin']  # Можно расширить список
        
        # Получаем пользователя из базы данных
        user = session.query(User).filter(User.user_id == user_id).first()
        if user and user.username and user.username in admin_usernames:
            return True
            
        # Дополнительная проверка для списка известных ID администраторов
        admin_ids = ['123456789', '987654321']  # Здесь нужно указать реальные ID администраторов
        if str(user_id) in admin_ids:
            return True
            
        return False
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса администратора: {str(e)}")
        return False
    finally:
        session.close()

# Обновим функцию update_subscription_status для отмены напоминания при обнаружении подписки
def update_subscription_status(user_id, context, send_welcome=False):
    """
    Проверяет статус подписки пользователя в локальной базе данных.
    
    Args:
        user_id: ID пользователя в Telegram
        context: CallbackContext
        send_welcome: Отправлять ли приветственное сообщение при активной подписке
        
    Returns:
        bool: True если подписка активна, False в противном случае
    """
    session = get_session()
    user = session.query(User).filter(User.user_id == user_id).first()
    
    if not user:
        session.close()
        return False
    
    is_subscribed = False
    
    if user.is_subscribed and user.subscription_expires:
        # Преобразуем в aware datetime если нужно
        expiry_date = make_aware(user.subscription_expires)
        now = datetime.now(TIMEZONE)
        
        if expiry_date > now:
            is_subscribed = True
            
            # Отправляем приветственное сообщение, если флаг установлен
            if send_welcome and context:
                # Отправляем приветственное сообщение в отдельном потоке
                threading.Thread(
                    target=send_welcome_subscription_messages,
                    args=(context, user_id)
                ).start()
        else:
            # Подписка истекла, обновляем статус
            user.is_subscribed = False
            session.commit()
    
    session.close()
    return is_subscribed

def check_subscription_status(user_id):
    """
    Проверяет статус подписки пользователя только в локальной базе данных.
    Airtable больше не используется.
    """
    session = get_session()
    user = session.query(User).filter(User.user_id == user_id).first()
    
    if user and user.is_subscribed and user.subscription_expires:
        # Преобразуем в aware datetime если нужно
        expiry_date = make_aware(user.subscription_expires)
        now = datetime.now(TIMEZONE)
        
        if expiry_date > now:
            paid_till = expiry_date.strftime("%Y-%m-%d")
            session.close()
            return True, paid_till
    
    session.close()
    return False, None

# Команда для проверки статуса подписки
def check_subscription(update: Update, context: CallbackContext):
    """Команда для ручной проверки статуса подписки."""
    user_id = update.effective_user.id
    is_subscribed = update_subscription_status(user_id, context, send_welcome=True)
    
    if is_subscribed:
        update.message.reply_text(
            "У вас активная подписка! ✅\n"
            "Вы имеете доступ ко всем функциям бота."
        )
    else:
        update.message.reply_text(
            "У вас нет активной подписки. ❌\n"
            "Для доступа к полному функционалу необходимо оформить подписку:",
            reply_markup=get_payment_keyboard(user_id, context)
        )
    
    return ConversationHandler.END

# Функция для связывания аккаунта Telegram с данными из Airtable
def link_telegram_with_tilda(update: Update, context: CallbackContext):
    """
    Проверяет статус подписки пользователя.
    """
    user_id = update.effective_user.id
    
    update.message.reply_text(
        "Проверяю статус вашей подписки...\n"
        "Подождите, пожалуйста, это займет пару секунд."
    )
    
    # Проверяем статус подписки в локальной БД
    is_subscribed, paid_till = check_subscription_status(user_id)
    
    if is_subscribed:
        update.message.reply_text(
            f"Ваша подписка активна! ✅\n\n"
            f"Срок действия: до {paid_till}"
        )
    else:
        # Если нет активной подписки, предлагаем оформить
        update.message.reply_text(
            "У вас нет активной подписки.\n\n"
            "Для оформления подписки перейдите по ссылке ниже:",
            reply_markup=get_payment_keyboard(user_id, context)
        )
    
    return ConversationHandler.END

# Функция для показа главного меню
def show_menu(update: Update, context: CallbackContext):
    """Показывает главное меню бота."""
    user_id = update.effective_user.id
    logger.info(f"[MENU] Пользователь {user_id} открыл главное меню")
    
    # Проверяем подписку в базе данных
    is_subscribed = update_subscription_status(user_id, context)
    
    # Отправляем приветствие с reply клавиатурой (вместо inline кнопок)
    update.message.reply_text(
        "Рад видеть вас снова! Выберите действие из меню:",
        reply_markup=get_main_keyboard()
    )
    
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text('Регистрация отменена.')
    return ConversationHandler.END

def handle_text_messages(update: Update, context: CallbackContext):
    message = update.message
    text = message.text
    user_id = message.from_user.id
    
    if text == "Назад":
        logger.info(f"Пользователь {user_id} нажал кнопку 'Назад', возвращаемся в главное меню")
        return back_to_main_menu(update, context)
    
    if 'cancellation' in context.user_data:
        logger.info(f"Перенаправление сообщения пользователя {user_id} в обработчик отмены подписки: {text}")
        return False  # Пропускаем этот обработчик, позволяя обработчику отмены подписки обработать сообщение
    
    if text == "/reload" or text == "reload":
        if is_admin(user_id):
            return reload_config(update, context)
        return
    
    if context.user_data.get('health_assistant_active'):
        logger.info(f"Обработка сообщения для Health ассистента от пользователя {user_id}: {text}")
        forward_to_health_assistant(update, context)
        return
    
    if text == "Health ассистент":
        logger.info(f"Пользователь {user_id} нажал кнопку 'Health ассистент'")
        return health_assistant_button(update, context)
    
    if text == "Управление подпиской":
        logger.info(f"Пользователь {user_id} нажал кнопку 'Управление подпиской'")
        try:
            session = get_session()
            user_db = session.query(User).filter(User.user_id == user_id).first()
            
            if user_db:
                is_subscribed = user_db.is_subscribed
                subscription_type = user_db.subscription_type
                subscription_expires = user_db.subscription_expires
                
                if is_subscribed and subscription_expires:
                    expires_date = subscription_expires.strftime("%d.%m.%Y")
                    remaining_days = (subscription_expires - datetime.now()).days
                    
                    sub_type = "месячная" if subscription_type == "monthly" else "годовая"
                    
                    config = get_bot_config()
                    manager_username = config.get("manager_username", "willway_manager")
                    
                    keyboard = [
                        [InlineKeyboardButton("Продлить подписку", callback_data="renew_subscription")],
                        [get_cancel_subscription_button()]
                    ]
                    
                    # Отправляем информацию о подписке
                    update.message.reply_text(
                        f"💎 *Информация о подписке*\n\n"
                        f"• Тип: {sub_type}\n"
                        f"• Активна до: {expires_date}\n"
                        f"• Осталось дней: {remaining_days}\n\n"
                        f"Для отмены подписки нажмите соответствующую кнопку ниже.",
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    # Если подписка не активна
                    update.message.reply_text(
                        "У вас нет активной подписки.\n\n"
                        "Оформите подписку для доступа к Health ассистенту и другим функциям бота:",
                        reply_markup=get_payment_keyboard_inline(user_id)
                    )
            else:
                # Если данные о пользователе не найдены
                update.message.reply_text(
                    "Не удалось получить информацию о вашей подписке. Пожалуйста, попробуйте позже.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_to_menu")]])
                )
        except Exception as e:
            logger.error(f"Ошибка при получении информации о подписке: {e}")
            update.message.reply_text(
                "Произошла ошибка при загрузке информации о подписке. Пожалуйста, попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_to_menu")]])
            )
        finally:
            if 'session' in locals() and session:
                session.close()
        return
    
    # Обработка кнопки "Связь с поддержкой"
    if text == "Связь с поддержкой":
        logger.info(f"Пользователь {user_id} нажал кнопку 'Связь с поддержкой'")
        update.message.reply_text(
            "Выберите с кем хотите связаться:",
            reply_markup=support_keyboard()
        )
        return
    
    # Обработка кнопки "Пригласить друга"
    if text == "Пригласить друга":
        logger.info(f"Пользователь {user_id} нажал кнопку 'Пригласить друга'")
        # Получаем реферальный код пользователя из БД и показываем полную информацию
        session = get_session()
        try:
            # Проверяем, есть ли у пользователя реферальный код
            ref_code = session.query(ReferralCode).filter(
                ReferralCode.user_id == user_id, 
                ReferralCode.is_active == True
            ).first()
            
            if not ref_code:
                # Если кода нет, генерируем новый
                import random
                import string
                new_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                
                ref_code = ReferralCode(
                    user_id=user_id,
                    code=new_code,
                    is_active=True
                )
                session.add(ref_code)
                session.commit()
                
                code = new_code
                logger.info(f"[REFERRAL] Создан новый реферальный код {code} для пользователя {user_id}")
            else:
                code = ref_code.code
                logger.info(f"[REFERRAL] Найден существующий реферальный код {code} для пользователя {user_id}")
            
            # Получаем ID пользователя в базе данных
            user_db = session.query(User).filter(User.user_id == user_id).first()
            if not user_db:
                logger.error(f"[REFERRAL_ERROR] Пользователь с ID {user_id} не найден в БД")
                raise Exception("Пользователь не найден в базе данных")
                
            # Получаем количество приглашенных друзей
            total_invited = 0
            paid_friends = 0
            
            # Попытка 1: По полю referrer_id == user_id (telegram ID)
            try:
                total_invited = session.query(ReferralUse).filter(
                    ReferralUse.referrer_id == user_id
                ).count()
                
                paid_friends = session.query(ReferralUse).filter(
                    ReferralUse.referrer_id == user_id,
                    ReferralUse.subscription_purchased == True
                ).count()
                
                logger.info(f"[REFERRAL] Статистика по Telegram ID: всего={total_invited}, с подпиской={paid_friends}")
            except Exception as e:
                logger.warning(f"[REFERRAL_WARNING] Ошибка при получении статистики по Telegram ID: {str(e)}")
            
            # Если не нашли по прямому ID, пробуем через ID в БД
            if total_invited == 0:
                try:
                    total_invited = session.query(ReferralUse).filter(
                        ReferralUse.referrer_id == user_db.id
                    ).count()
                    
                    paid_friends = session.query(ReferralUse).filter(
                        ReferralUse.referrer_id == user_db.id,
                        ReferralUse.subscription_purchased == True
                    ).count()
                    
                    logger.info(f"[REFERRAL] Статистика по ID в БД: всего={total_invited}, с подпиской={paid_friends}")
                except Exception as e:
                    logger.warning(f"[REFERRAL_WARNING] Ошибка при получении статистики по ID в БД: {str(e)}")
            
            # Получаем имя бота
            bot_username = os.environ.get('TELEGRAM_BOT_USERNAME', 'willwayapp_bot')  # Получаем из переменной окружения
            try:
                bot_info = context.bot.get_me()
                bot_username = bot_info.username
            except:
                logger.error("Не удалось получить username бота")
            
            # Формируем реферальную ссылку
            referral_link = f"https://t.me/{bot_username}?start={code}"
            
            # Получаем клавиатуру и ссылку
            keyboard, referral_link = get_referral_keyboard(user_id, code)
            
            # Формируем простое сообщение без эмодзи и сложного форматирования, но с ссылкой
            message = (
                "Приглашайте друзей и получайте бонусы!\n\n"
                "За каждого друга, который оформит подписку, "
                "вы получите +1 месяц к вашей текущей подписке.\n\n"
                "Статистика:\n"
                f"- Всего приглашено друзей: {total_invited}\n"
                f"- Друзей с подпиской: {paid_friends}\n"
                f"- Бонусных месяцев получено: {paid_friends}\n\n"
                f"Ваша реферальная ссылка: {referral_link}\n\n"
                f"Ваш реферальный код: {code}"
            )
            
            # Создаем клавиатуру
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Назад", callback_data="back_to_menu")]
            ])
            
            # Отправляем сообщение
            context.bot.send_message(
                chat_id=user_id,
                text=message,
                reply_markup=keyboard
            )
            
        except Exception as e:
            logger.error(f"[REFERRAL_ERROR] Ошибка при обработке приглашения друга: {str(e)}")
            update.message.reply_text(
                text="Произошла ошибка при получении вашей реферальной ссылки. Пожалуйста, попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_to_menu")]])
            )
        finally:
            session.close()
        return
        
    # Проверяем активную подписку пользователя
    session = get_session()
    try:
        user_db = session.query(User).filter(User.user_id == user_id).first()
        
        if not user_db or not user_db.is_subscribed:
            logger.info(f"Пользователь {user_id} пытается использовать Health ассистента без подписки")
            
            # Если нет подписки, показываем сообщение о необходимости подписки
            if context.user_data.get('health_assistant_active'):
                # Сбрасываем флаг активности Health ассистента
                context.user_data['health_assistant_active'] = False
                
                update.message.reply_text(
                    "Для использования Health ассистента необходима активная подписка.\n\n"
                    "Оформите подписку, чтобы получить доступ:",
                    reply_markup=get_payment_keyboard_inline(user_id)
                )
            return
    except Exception as e:
        logger.error(f"Ошибка при проверке подписки для Health ассистента: {e}")
    finally:
        session.close()
    
    # Если ни один из обработчиков не сработал, выводим главное меню
    logger.info(f"Неизвестное сообщение от пользователя {user_id}, возвращаем главное меню")
    show_menu(update, context)

def cancel_payment_reminder(context, user_id):
    jobs = context.job_queue.get_jobs_by_name(f"payment_reminder_{user_id}")
    for job in jobs:
        job.schedule_removal()
        logger.info(f"Напоминание о подписке для пользователя {user_id} отменено")

def send_welcome_subscription_messages(context, user_id):
    logger.info(f"[SUBSCRIPTION_WELCOME] Отправка приветственного сообщения пользователю {user_id}")
    
    try:
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            logger.error(f"[SUBSCRIPTION_WELCOME] Пользователь {user_id} не найден в базе данных")
            return
        
        config = get_bot_config()
        channel_url = config.get("channel_url", "https://t.me/willway_channel")
        
        welcome_text = (
            "Добро пожаловать в WILLWAY!\n\n"
            "Я твой персональный помощник. Я помогу тебе достичь твоих целей "
            "в фитнесе и здоровом образе жизни.\n\n"
            "Чтобы начать, тебе нужно заполнить короткую анкету. "
            "Это поможет мне лучше понять твои цели и подобрать "
            "оптимальную программу тренировок."
        )
        
        # Клавиатура с кнопками для приложения и канала
        keyboard = [
            [InlineKeyboardButton("Доступ к приложению", url="https://willway.pro/")],
            [InlineKeyboardButton("Вступить в канал", url=channel_url)]
        ]
        
        # Отправляем сообщение с кнопками
        context.bot.send_message(
            chat_id=user_id,
            text=welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        logger.info(f"[SUBSCRIPTION_WELCOME] Успешно отправлено приветственное сообщение пользователю {user_id}")
    except Exception as e:
        logger.error(f"[SUBSCRIPTION_WELCOME_ERROR] Ошибка при отправке приветственного сообщения: {e}")
    finally:
        if 'session' in locals():
            session.close()

# Добавляем функцию для активации тестовой подписки
def activate_test_subscription(update: Update, context: CallbackContext):
    """Обработчик для тестовой активации подписки (только для тестирования)."""
    query = update.callback_query
    query.answer()
    
    # Получаем ID пользователя из callback_data
    callback_data = query.data
    user_id = callback_data.split('_')[2]
    
    try:
        user_id = int(user_id)
    except ValueError:
        logger.error(f"Некорректный ID пользователя в callback_data: {callback_data}")
        query.edit_message_text("Ошибка активации тестовой подписки. Попробуйте снова.")
        return
    
    # Отменяем напоминание о незавершенной подписке, если оно было запланировано
    cancel_payment_reminder(context, user_id)
    
    # Активируем подписку в базе данных
    session = get_session()
    user = session.query(User).filter(User.user_id == user_id).first()
    
    if not user:
        logger.error(f"Пользователь с ID {user_id} не найден в базе данных")
        query.edit_message_text("Ошибка: пользователь не найден. Начните регистрацию с команды /start")
        session.close()
        return
    
    # Устанавливаем подписку на 30 дней
    user.is_subscribed = True
    user.subscription_expires = datetime.now(TIMEZONE) + timedelta(days=30)
    expiry_date = user.subscription_expires.strftime("%d.%m.%Y")
    
    session.commit()
    logger.info(f"Активирована тестовая подписка для пользователя {user_id} до {expiry_date}")
    session.close()
    
    # Сообщаем пользователю об успешной активации подписки
    query.edit_message_text(
        f"✅ Тестовая подписка успешно активирована!\n\n"
        f"Статус: Активна\n"
        f"Действует до: {expiry_date}\n\n"
        f"Теперь вы можете пользоваться всеми функциями бота."
    )
    
    # Отправляем серию приветственных сообщений
    send_welcome_subscription_messages(context, user_id)
    
# Клавиатуры для различных шагов
def gender_keyboard():
    """Клавиатура для выбора пола."""
    keyboard = [
        [InlineKeyboardButton("Мужской", callback_data="male")],
        [InlineKeyboardButton("Женский", callback_data="female")]
    ]
    return InlineKeyboardMarkup(keyboard)

def main_goal_keyboard():
    keyboard = [
        [InlineKeyboardButton("☑️ Снижение веса", callback_data="goal_1")],
        [InlineKeyboardButton("☑️ Набор мышечной массы", callback_data="goal_2")],
        [InlineKeyboardButton("☑️ Коррекция осанки", callback_data="goal_3")],
        [InlineKeyboardButton("☑️ Убрать зажатость в теле", callback_data="goal_4")],
        [InlineKeyboardButton("☑️ Общий тонус/рельеф мышц", callback_data="goal_5")],
        [InlineKeyboardButton("☑️ Восстановиться после родов", callback_data="goal_6")],
        [InlineKeyboardButton("☑️ Снять эмоциональное напряжение", callback_data="goal_7")],
        [InlineKeyboardButton("☑️ Улучшить качество сна", callback_data="goal_8")],
        [InlineKeyboardButton("☑️ Стать более энергичным", callback_data="goal_9")],
        [InlineKeyboardButton("Готово ✓", callback_data="goals_done")]
    ]
    return InlineKeyboardMarkup(keyboard)

def additional_goal_keyboard():
    keyboard = [
        [InlineKeyboardButton("☑️ Послушать лекции от врачей, тренеров", callback_data="add_goal_1")],
        [InlineKeyboardButton("☑️ Послушать лекции от проф психологов", callback_data="add_goal_2")],
        [InlineKeyboardButton("☑️ Больше узнать о здоровом питании", callback_data="add_goal_3")],
        [InlineKeyboardButton("☑️ Добавить в свою жизнь медитации, практики", callback_data="add_goal_4")],
        [InlineKeyboardButton("☑️ Обрести новые знакомства", callback_data="add_goal_5")],
        [InlineKeyboardButton("☑️ Поддержка, обратная связь, мотивация", callback_data="add_goal_6")],
        [InlineKeyboardButton("Готово ✓", callback_data="additional_goals_done")]
    ]
    return InlineKeyboardMarkup(keyboard)

def work_format_keyboard():
    keyboard = [
        [InlineKeyboardButton("Много сижу за компьютером", callback_data="Сидячая работа")],
        [InlineKeyboardButton("Мама в декрете", callback_data="Мама в декрете")],
        [InlineKeyboardButton("Не работаю (на раслабоне, на чиле)", callback_data="Не работаю")],
        [InlineKeyboardButton("Частые командировки", callback_data="Частые командировки")],
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
    """Клавиатура для выбора варианта подписки."""
    # Используем клавиатуру из модуля сомнений при выборе подписки
    from bot.subscription_doubt_handler import get_subscription_keyboard
    return get_subscription_keyboard()
    
def get_incomplete_payment_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("Главное меню", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def send_incomplete_payment_reminder(context: CallbackContext):
    logger.info("[PAYMENT_DISABLED] Функция отправки напоминаний о незавершенной оплате отключена")
    return

def schedule_payment_reminder(context, user_id, delay_minutes=0.02):
    logger.info("[PAYMENT_DISABLED] Функция планирования напоминаний о незавершенной оплате отключена")
    return

def send_test_reminder(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    update.message.reply_text(
        "Тестовое напоминание о подписке будет отправлено через 1 минуту"
    )
    
    schedule_payment_reminder(context, user_id, delay_minutes=1)
    
def main_goal_texts():
    return {
        "Убрать лишний вес": "Твоя программа уже составлена 🏆 \n\nЧтобы достичь цели «Убрать лишний вес» мы будем работать в 3-х направлениях:\n\n1️⃣ Тренировки\n✓ 3 месяца с тренером он-лайн\n✓ Индивидуальная программа\n✓ обратная связь по технике и нагрузке\n✓ корректировка программы\n\n2️⃣ Питание\n✓ подбор плана питания исходя из целей\n✓ дневник питания\n✓ обратная связь\n✓ лекции о правильном питании\n\n3️⃣ Образ жизни\n✓ лекции о стрессе, сне, укреплении иммунитета\n✓ лекции о мотивации и режиме\n\nСтоимость такой программы 7 990 руб. за 3 месяца.",
        "Набрать мышечную массу": "Твоя программа уже составлена 🏆 \n\nЧтобы достичь цели «Набрать мышечную массу» мы будем работать в 3-х направлениях:\n\n1️⃣ Тренировки\n✓ 3 месяца с тренером он-лайн\n✓ Составление программы с учётом всех мышечных групп, объема нагрузки\n✓ Подбор упражнений, акцентов и дополнительных движений, если есть отстающие группы мышц\n✓ обратная связь по технике и нагрузке\n✓ корректировка программы через каждые 3 недели\n\n2️⃣ Питание\n✓ подбор плана питания исходя из целей\n✓ калькуляция КБЖУ и рекомендуемых продуктов\n✓ дневник питания\n✓ обратная связь\n✓ лекции о правильном питании для эффективного набора массы\n\n3️⃣ Образ жизни\n✓ лекции о стрессе, сне, нервной регуляции\n✓ лекции о мотивации и режиме\n\nСтоимость такой программы 7 990 руб. за 3 месяца.",
        "Повысить выносливость": "Твоя программа уже составлена 🏆 \n\nЧтобы достичь цели «Повысить выносливость» мы будем работать в 3-х направлениях:\n\n1️⃣ Тренировки\n✓ 3 месяца с тренером он-лайн\n✓ Индивидуальная программа\n✓ сопровождение и корректировка программы\n✓ обратная связь по нагрузкам\n\n2️⃣ Питание\n✓ подбор плана питания исходя из целей\n✓ дневник питания\n✓ обратная связь\n✓ рекомендации по восстановлению, микроэлементам\n\n3️⃣ Образ жизни\n✓ лекции о стрессе, сне, укреплении иммунитета\n✓ лекции о мотивации и режиме\n\nСтоимость такой программы 7 990 руб. за 3 месяца."
    }

def additional_goal_texts():
    return {
        "Послушать лекции от врачей, тренеров": "Ты получишь доступ к лекциям от врачей и тренеров по темам здоровья, тренировок и реабилитации.",
        "Послушать лекции от проф психологов": "В программу включены лекции от профессиональных психологов о мотивации, преодолении барьеров и психологии здорового образа жизни.",
        "Больше узнать о здоровом питании": "Тебя ждут подробные материалы о здоровом питании, составлении рациона и правильном подходе к приему пищи.",
        "Добавить в свою жизнь медитации, практики": "Программа содержит медитации и практики для улучшения психологического состояния и снижения стресса.",
        "Обрести новые знакомства": "Ты станешь частью сообщества единомышленников, где сможешь общаться и заводить новые знакомства.",
        "Поддержка, обратная связь, мотивация": "Персональная поддержка тренера, регулярная обратная связь и мотивационные материалы помогут тебе достичь целей."
    }
    

def webhook_handler(update: Update, context: CallbackContext):
    logger.info("[PAYMENT_DISABLED] Получен webhook (система оплаты отключена)")
    return

def create_payment_record(user_id, subscription_type, payment_amount, payment_status='pending'):
    logger.info(f"[PAYMENT_DISABLED] Попытка создания записи о платеже (пользователь {user_id}, тип {subscription_type})")
    return False

def generate_payment_url(user_id, subscription_type):
    logger.info(f"[PAYMENT_DISABLED] Попытка генерации URL оплаты (пользователь {user_id}, тип {subscription_type})")
    return None

def send_successful_payment_messages(update: Update, context: CallbackContext, subscription_status):
    user_id = update.effective_user.id if update else context.user_data.get('user_id')
    logger.info(f"[PAYMENT_DISABLED] Попытка отправки сообщений об успешной оплате (пользователь {user_id})")
    return

def send_payment_processing_messages(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    logger.info(f"[PAYMENT_DISABLED] Попытка отправки сообщений о обработке платежа (пользователь {user_id})")
    return

def check_payment_status_job(context: CallbackContext):
    logger.info("[PAYMENT_DISABLED] Попытка проверки статуса платежа")
    return

def handle_support_messages(update, context):
    text = update.message.text
    user_id = update.effective_user.id
    logger.info(f"Пользователь {user_id} в меню поддержки выбрал: {text}")

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
    user_id = update.effective_user.id
    text = update.message.text
    logger.info(f"[OTHER_MESSAGE] Получено необработанное сообщение от пользователя {user_id}: {text}")
    
    if text == "Подобрать персональную программу":
        logger.info(f"[SURVEY_START] Пользователь {user_id} нажал на кнопку 'Подобрать персональную программу'")
        return start_survey(update, context)
    
    update.message.reply_text(
        "Извините, я не понимаю эту команду. Пожалуйста, используйте меню для взаимодействия с ботом.",
        reply_markup=get_main_keyboard()
    )

def send_subscription_expiration_reminder(context: CallbackContext):
    message = (
        "Привет! Напоминаю, что срок действия твоей подписки подходит к концу.\n\n"
        "Для того, чтобы продолжить пользоваться всеми функциями бота, "
        "тебе нужно продлить подписку."
    )

PAYMENT_STATUS = {
    'PENDING': 'pending',
    'PROCESSING': 'processing',
    'COMPLETED': 'completed',
    'FAILED': 'failed',
    'CANCELLED': 'cancelled',
    'REDIRECTED': 'redirected',
    'EXPIRED': 'expired'
}

PAYMENT_SCENARIOS = {
    'SUCCESS': 'success',
    'TIMEOUT': 'timeout',
    'ERROR': 'error',
    'CANCEL': 'cancel'
}

MONTHLY_SUBSCRIPTION_PRICE = 1555
YEARLY_SUBSCRIPTION_PRICE = 13333

class PaymentTracker:
    def __init__(self, session=None):
        self.session = session
        
    def log_payment_event(self, user_id, event_type, payment_id=None, status=None, data=None):
        return None
        
    def track_payment_initiation(self, user_id, amount, subscription_type, payment_data=None):
        return None
        
    def track_payment_redirect(self, user_id, payment_id, payment_url):
        return None
        
    def track_payment_completion(self, user_id, payment_id, status, amount=None, subscription_type=None, subscription_expires=None, payment_data=None):
        return None
        
    def track_payment_error(self, user_id, payment_id, error_message, payment_data=None):
        return None
        
    def get_payment_status(self, user_id):
        return {'status': 'disabled'}
        
    def run_payment_scenario(self, scenario_type, user_id, payment_id=None):
        return None

class PaymentHandler:
    def __init__(self):
        pass
        
    def generate_tilda_payment_link(self, user_data, subscription_type):
        user_id = user_data.get('user_id')
        base_url = "https://willway.pro/"
        return f"{base_url}?tgid={user_id}&subscription_type={subscription_type}"

class CloudPaymentAdapter:
    def __init__(self):
        pass
        
        
    def generate_payment_url(self, amount, currency, invoice_id, description, account_id, email, data=None):
        return None

def get_payment_keyboard_inline(user_id):
    # Форматируем цены с разделителями тысяч и символом рубля
    # Отключаем локаль, потому что она может вызывать проблемы с совместимостью
    # locale.setlocale(locale.LC_ALL, 'ru_RU.UTF-8')
    
    # Ручная форматирование с пробелом как разделитель тысяч
    # Function to format prices with space thousands separator and ruble sign
    def format_price(price):
        # Convert to string and split into integer and decimal parts
        price_str = str(price)
        parts = price_str.split('.')
        integer_part = parts[0]
        
        # Format the integer part with space as thousand separator
        if len(integer_part) > 3:
            formatted = integer_part[:-3] + ' ' + integer_part[-3:]
        else:
            formatted = integer_part
            
        return formatted + " ₽"
        
    monthly_price = format_price(MONTHLY_SUBSCRIPTION_PRICE)
    yearly_price = format_price(YEARLY_SUBSCRIPTION_PRICE)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Доступ к приложению", url="https://willway.pro/")],
        [InlineKeyboardButton(f"Месячная подписка - {monthly_price}", callback_data=f"pay_monthly_{user_id}")],
        [InlineKeyboardButton(f"Годовая подписка - {yearly_price} (скидка 28%)", callback_data=f"pay_yearly_{user_id}")],
    ])
    
    return keyboard

def save_bot_config(config):
    try:
        BOT_CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bot_config.json')
        
        with open(BOT_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        
        logger.info(f"Конфигурация бота успешно сохранена в файл {BOT_CONFIG_FILE}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении конфигурации бота: {e}")
        return False

def help_command(update: Update, context: CallbackContext):
    message = (
        "Привет! Я твой помощник в WILLWAY.\n\n"
        "Если у тебя возникли вопросы или тебе нужна помощь, "
        "ты всегда можешь связаться с нашей поддержкой:"
    )

__all__ = ['get_bot_config']

def get_referral_keyboard(user_id, ref_code):
    """Генерирует клавиатуру для реферальной программы и ссылку"""
    # Получаем имя бота из переменной окружения
    bot_username = os.environ.get('TELEGRAM_BOT_USERNAME', 'willwayapp_bot')
    referral_link = f"https://t.me/{bot_username}?start={ref_code}"
    
    # Создаем простую клавиатуру только с кнопкой Назад
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Назад", callback_data="back_to_menu")]
    ])
    
    return keyboard, referral_link

def invite_friend(update: Update, context: CallbackContext):
    """Максимально простая заглушка"""
    user_id = update.effective_user.id
    
    # Определяем тип запроса
    if update.callback_query:
        query = update.callback_query
        query.answer()
        message_sender = query.edit_message_text
    else:
        query = None
        message_sender = lambda text, reply_markup: context.bot.send_message(
            chat_id=user_id, text=text, reply_markup=reply_markup)
    
    # Создаем очень простое сообщение
    message = "Ваш реферальный код: 3ROCO71M"
    
    # Простая клавиатура
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_to_menu")]])
    
    # Отправляем сообщение
    try:
        message_sender(message, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"[REFERRAL_ERROR] Ошибка: {str(e)}")
        # В случае ошибки пробуем отправить новое сообщение
        if query:
            context.bot.send_message(
                chat_id=user_id,
                text="Произошла ошибка. Повторите позже.",
                reply_markup=keyboard
            )
        else:
            # Если это уже было обычное сообщение, то просто логируем ошибку
            pass

def handle_copy_ref_link(update: Update, context: CallbackContext):
    """Максимально простая заглушка"""
    query = update.callback_query
    query.answer("Код скопирован!")
    
    # Простой хак - просто отправить новое сообщение вместо редактирования текущего
    context.bot.send_message(
        chat_id=update.effective_user.id,
        text="Ваш реферальный код: 3ROCO71M",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_to_menu")]])
    )

def show_referral_stats(update: Update, context: CallbackContext):
    """Максимально простая заглушка"""
    query = update.callback_query
    query.answer()
    
    # Используем тот же примитивный подход
    context.bot.send_message(
        chat_id=update.effective_user.id,
        text="Ваш реферальный код: 3ROCO71M",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_to_menu")]])
    )

def handle_show_subscription_options(update: Update, context: CallbackContext):
    """
    Обработчик нажатия на кнопку "Варианты WILLWAY подписки:"
    Показывает варианты подписки с использованием обработчика сомнений
    """
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    logger.info(f"[CALLBACK] Пользователь {user_id} нажал кнопку 'Варианты WILLWAY подписки:'")
    
    # Импортируем функцию из модуля subscription_doubt_handler
    # Импорт внутри функции, чтобы избежать циклического импорта
    from bot.subscription_doubt_handler import get_subscription_keyboard
    
    # Показываем варианты подписки с возможностью выбрать "Подумаю"
    # Передаем user_id для генерации правильных ссылок с Telegram ID
    try:
        query.edit_message_text(
            text="Варианты WILLWAY подписки:",
            reply_markup=get_subscription_keyboard(user_id)
        )
    except Exception as e:
        logger.error(f"Ошибка при редактировании сообщения для вариантов подписки: {str(e)}")
        # В случае ошибки отправляем новое сообщение вместо редактирования
        context.bot.send_message(
            chat_id=user_id,
            text="Варианты WILLWAY подписки:",
            reply_markup=get_subscription_keyboard(user_id)
        )

def forward_to_health_assistant(update: Update, context: CallbackContext):
    """
    Перенаправляет сообщение на обработку в Health ассистент
    """
    logger.info(f"Перенаправление сообщения в Health ассистент")
    handle_health_assistant_message(update, context)
    return

def get_health_assistant_response(user_id, user_message, conversation_history):
    """
    Получает ответ от Health ассистента
    
    В этой версии использует реальный API для получения ответа.
    """
    logger.info(f"Запрос к Health ассистенту от пользователя {user_id}: {user_message}")
    
    try:
        # Попытаемся получить ответ от GPT напрямую из модуля gpt_assistant
        from bot.gpt_assistant import get_health_assistant_response as get_ai_response
        
        # Получаем ответ от GPT
        response = get_ai_response(user_id, user_message, conversation_history)
        
        # Если ответ получен успешно, возвращаем его
        if response:
            return response
    except Exception as e:
        logger.error(f"Ошибка при обращении к API GPT: {e}")
    
    # Если произошла ошибка или ответ не получен, возвращаем заглушку
    return "Извините, Health ассистент временно недоступен из-за технических работ. Пожалуйста, попробуйте позже."
