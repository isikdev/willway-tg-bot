#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Точка входа для запуска бота блогеров
"""

import os
import logging
import sys
import json
import threading
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import Updater, CommandHandler, CallbackContext, CallbackQueryHandler
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('blogger_bot.log')
    ]
)

logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

def get_bot_config():
    """Загружает конфигурацию бота"""
    try:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'blogger_bot_config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"Конфигурация загружена: {list(config.keys())}")
                return config
        else:
            logger.error(f"Файл конфигурации не найден: {config_path}")
            return {}
    except Exception as e:
        logger.error(f"Ошибка при загрузке конфигурации: {e}")
        return {}

def apply_bot_config(bot, config):
    """Применяет настройки из конфигурации к боту"""
    logger.info("Применение настроек бота блогеров...")
    
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
                    # Устанавливаем команды
                    bot.set_my_commands(bot_commands)
                    logger.info(f"Обновлены команды бота блогеров: {bot_commands}")
                except Exception as e:
                    logger.error(f"Ошибка при обновлении команд бота блогеров: {e}")
        
        # Настройки для API Telegram (без использования aiogram)
        try:
            token = config.get("bot_token") or os.getenv("BLOGGER_BOT_TOKEN")
            if token:
                import requests
                api_url = f"https://api.telegram.org/bot{token}"
                
                # Обновление имени бота
                if "bot_name" in config:
                    response = requests.post(f"{api_url}/setMyName", data={"name": config["bot_name"]})
                    if response.status_code == 200 and response.json().get("ok"):
                        logger.info(f"Имя бота блогеров успешно обновлено: {config['bot_name']}")
                
                # Обновление описания бота
                if "description" in config:
                    response = requests.post(f"{api_url}/setMyDescription", data={"description": config["description"]})
                    if response.status_code == 200 and response.json().get("ok"):
                        logger.info("Описание бота блогеров успешно обновлено")
                
                # Обновление "О боте"
                if "about_text" in config:
                    response = requests.post(f"{api_url}/setMyShortDescription", data={"short_description": config["about_text"]})
                    if response.status_code == 200 and response.json().get("ok"):
                        logger.info("Информация 'О боте' для бота блогеров успешно обновлена")
            else:
                logger.warning("Не найден токен бота блогеров для применения настроек через API Telegram")
        except Exception as e:
            logger.error(f"Ошибка при применении настроек бота блогеров через API Telegram: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при применении конфигурации к боту блогеров: {e}")
        return False

def start(update: Update, context: CallbackContext) -> None:
    """Обрабатывает команду /start"""
    config = get_bot_config()
    webapp_url = config.get("webapp_url", "https://bloggers.api-willway.ru/blogger/login")
    admin_username = config.get("admin_username", "Jackturaa")
    
    user = update.effective_user
    
    # Создаем кнопку для запуска веб-приложения
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Запустить личный кабинет", web_app=WebAppInfo(url=webapp_url))]
    ])
    
    # Отправляем приветственное сообщение
    update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Добро пожаловать в официальный бот WILLWAY для блогеров-партнёров!\n\n"
        "Чтобы открыть личный кабинет блогера, нажмите кнопку ниже. "
        "Там вы сможете получить уникальную реферальную ссылку, следить за статистикой переходов "
        "и получать 20% комиссии с каждой продажи.\n\n"
        f"Если у вас возникли вопросы, обратитесь к администратору: @{admin_username}",
        reply_markup=keyboard
    )

def delete_webhook(token):
    """Удаляет webhook для бота"""
    try:
        import requests
        # Удаляем вебхук
        webhook_url = f"https://api.telegram.org/bot{token}/deleteWebhook"
        response = requests.get(webhook_url)
        if response.status_code == 200 and response.json().get("ok"):
            logger.info("Webhook для бота блогеров успешно удален")
            return True
        else:
            logger.warning(f"Ошибка при удалении webhook для бота блогеров: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Ошибка при попытке удалить webhook для бота блогеров: {e}")
        return False

def main():
    """Основная функция для запуска бота блогеров"""
    logger.info("Запуск бота блогеров WILLWAY")
    
    # Получаем токен бота
    config = get_bot_config()
    token = config.get("bot_token") or os.getenv("BLOGGER_BOT_TOKEN")
    
    if not token:
        logger.error("Токен бота блогеров не найден ни в конфигурации, ни в переменных окружения")
        return
    
    # Удаляем webhook для избежания конфликтов
    delete_webhook(token)
    
    # Создаем и настраиваем бота
    updater = Updater(token)
    dispatcher = updater.dispatcher
    
    # Регистрируем обработчики команд
    dispatcher.add_handler(CommandHandler("start", start))
    
    # Применяем настройки к боту
    apply_bot_config(updater.bot, config)
    
    # Запускаем бота
    updater.start_polling()
    logger.info("Бот блогеров запущен и ожидает сообщений")
    
    # Останавливаем бота при нажатии Ctrl+C
    updater.idle()

if __name__ == "__main__":
    main() 