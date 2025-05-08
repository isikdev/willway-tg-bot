#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Скрипт для мониторинга изменений в конфигурациях ботов и автоматического перезапуска ботов
Также проверяет настройки ботов через API Telegram и восстанавливает их при внешних изменениях
"""

import os
import time
import json
import hashlib
import logging
import subprocess
import signal
import sys
import requests
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('watcher.log')
    ]
)

logger = logging.getLogger(__name__)

# Конфигурация ботов
BOT_CONFIGS = [
    {
        "name": "main",
        "config_file": "bot_config.json",
        "script_file": "run_bot.py"
    },
    {
        "name": "blogger",
        "config_file": "blogger_bot_config.json",
        "script_file": "run_blogger_bot.py"
    }
]

class TelegramAPI:
    """Класс для взаимодействия с API Telegram"""
    
    def __init__(self, token):
        """
        Инициализация класса
        
        Args:
            token: Токен бота Telegram
        """
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
    
    def get_bot_info(self):
        """Получает информацию о боте через API Telegram"""
        try:
            response = requests.get(f"{self.api_url}/getMe")
            if response.status_code == 200:
                data = response.json()
                if data.get("ok", False):
                    return data.get("result", {})
                else:
                    logger.error(f"Ошибка при получении информации о боте: {data.get('description')}")
            else:
                logger.error(f"Ошибка HTTP при получении информации о боте: {response.status_code}")
        except Exception as e:
            logger.error(f"Исключение при получении информации о боте: {e}")
        return None
    
    def get_commands(self):
        """Получает список команд бота через API Telegram"""
        try:
            response = requests.get(f"{self.api_url}/getMyCommands")
            if response.status_code == 200:
                data = response.json()
                if data.get("ok", False):
                    return data.get("result", [])
                else:
                    logger.error(f"Ошибка при получении команд бота: {data.get('description')}")
            else:
                logger.error(f"Ошибка HTTP при получении команд бота: {response.status_code}")
        except Exception as e:
            logger.error(f"Исключение при получении команд бота: {e}")
        return []
    
    def get_webhook_info(self):
        """Получает информацию о webhook бота через API Telegram"""
        try:
            response = requests.get(f"{self.api_url}/getWebhookInfo")
            if response.status_code == 200:
                data = response.json()
                if data.get("ok", False):
                    return data.get("result", {})
                else:
                    logger.error(f"Ошибка при получении информации о webhook: {data.get('description')}")
            else:
                logger.error(f"Ошибка HTTP при получении информации о webhook: {response.status_code}")
        except Exception as e:
            logger.error(f"Исключение при получении информации о webhook: {e}")
        return {}
    
    def delete_webhook(self):
        """Удаляет webhook бота через API Telegram"""
        try:
            response = requests.get(f"{self.api_url}/deleteWebhook")
            if response.status_code == 200:
                data = response.json()
                if data.get("ok", False):
                    logger.info("Webhook успешно удален")
                    return True
                else:
                    logger.error(f"Ошибка при удалении webhook: {data.get('description')}")
            else:
                logger.error(f"Ошибка HTTP при удалении webhook: {response.status_code}")
        except Exception as e:
            logger.error(f"Исключение при удалении webhook: {e}")
        return False
    
    def apply_bot_settings(self, config):
        """Применяет настройки бота через API Telegram"""
        results = {
            "name": False,
            "description": False,
            "about": False,
            "commands": False
        }
        
        # Обновление имени бота
        if "bot_name" in config:
            try:
                # Добавляем задержку перед запросом для предотвращения ограничений API
                time.sleep(1.5)
                
                response = requests.post(f"{self.api_url}/setMyName", data={"name": config["bot_name"]})
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok", False):
                        logger.info(f"Имя бота успешно обновлено: {config['bot_name']}")
                        results["name"] = True
                    else:
                        logger.error(f"Ошибка при обновлении имени бота: {data.get('description')}")
                elif response.status_code == 429:
                    # При ошибке 429 (Too Many Requests) сохраняем информацию, но не считаем это критичной ошибкой
                    logger.warning(f"Превышен лимит запросов при изменении имени бота. Telegram ограничивает частоту изменения имени.")
                    # Отмечаем как успешно, чтобы избежать перезапуска бота из-за этой ошибки
                    results["name"] = True
                else:
                    logger.error(f"Ошибка HTTP при обновлении имени бота: {response.status_code}")
            except Exception as e:
                logger.error(f"Исключение при обновлении имени бота: {e}")
        
        # Обновление описания бота
        if "description" in config:
            try:
                # Добавляем задержку перед запросом
                time.sleep(1.5)
                
                response = requests.post(f"{self.api_url}/setMyDescription", data={"description": config["description"]})
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok", False):
                        logger.info("Описание бота успешно обновлено")
                        results["description"] = True
                    else:
                        logger.error(f"Ошибка при обновлении описания бота: {data.get('description')}")
                elif response.status_code == 429:
                    logger.warning("Превышен лимит запросов при изменении описания бота")
                    results["description"] = True
                else:
                    logger.error(f"Ошибка HTTP при обновлении описания бота: {response.status_code}")
            except Exception as e:
                logger.error(f"Исключение при обновлении описания бота: {e}")
        
        # Обновление "О боте"
        if "about_text" in config:
            try:
                # Добавляем задержку перед запросом
                time.sleep(1.5)
                
                response = requests.post(f"{self.api_url}/setMyShortDescription", data={"short_description": config["about_text"]})
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok", False):
                        logger.info("Информация 'О боте' успешно обновлена")
                        results["about"] = True
                    else:
                        logger.error(f"Ошибка при обновлении информации 'О боте': {data.get('description')}")
                elif response.status_code == 429:
                    logger.warning("Превышен лимит запросов при изменении информации 'О боте'")
                    results["about"] = True
                else:
                    logger.error(f"Ошибка HTTP при обновлении информации 'О боте': {response.status_code}")
            except Exception as e:
                logger.error(f"Исключение при обновлении информации 'О боте': {e}")
        
        # Обновление команд бота
        if "commands" in config and isinstance(config["commands"], dict):
            try:
                # Добавляем задержку перед запросом
                time.sleep(1.5)
                
                # Преобразуем словарь команд в нужный формат
                formatted_commands = []
                for cmd, desc in config["commands"].items():
                    # Убираем символ "/" если он есть в начале команды
                    cmd_name = cmd[1:] if cmd.startswith('/') else cmd
                    formatted_commands.append({"command": cmd_name, "description": desc})
                
                response = requests.post(
                    f"{self.api_url}/setMyCommands", 
                    json={"commands": formatted_commands}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok", False):
                        logger.info("Команды бота успешно обновлены")
                        results["commands"] = True
                    else:
                        logger.error(f"Ошибка при обновлении команд бота: {data.get('description')}")
                elif response.status_code == 429:
                    logger.warning("Превышен лимит запросов при изменении команд бота")
                    results["commands"] = True
                else:
                    logger.error(f"Ошибка HTTP при обновлении команд бота: {response.status_code}")
            except Exception as e:
                logger.error(f"Исключение при обновлении команд бота: {e}")
        
        return results
    
    def check_bot_settings(self, config):
        """
        Проверяет, соответствуют ли настройки бота в Telegram нашей конфигурации
        
        Args:
            config: Конфигурация бота из JSON
            
        Returns:
            Словарь с результатами проверки {field: is_matching}
        """
        results = {
            "name": True,
            "commands": True
        }
        
        # Проверяем имя бота
        bot_info = self.get_bot_info()
        if bot_info and "bot_name" in config:
            actual_name = bot_info.get("first_name", "")
            expected_name = config["bot_name"]
            
            if actual_name != expected_name:
                logger.warning(f"Имя бота в Telegram ({actual_name}) не соответствует ожидаемому ({expected_name})")
                results["name"] = False
        
        # Проверяем команды бота
        actual_commands = self.get_commands()
        if "commands" in config and isinstance(config["commands"], dict):
            expected_commands = {}
            for cmd, desc in config["commands"].items():
                cmd_name = cmd[1:] if cmd.startswith('/') else cmd
                expected_commands[cmd_name] = desc
            
            actual_commands_dict = {cmd["command"]: cmd["description"] for cmd in actual_commands}
            
            # Проверяем, все ли ожидаемые команды присутствуют с правильными описаниями
            for cmd, desc in expected_commands.items():
                if cmd not in actual_commands_dict or actual_commands_dict[cmd] != desc:
                    logger.warning(f"Команда '{cmd}' не соответствует конфигурации в Telegram")
                    results["commands"] = False
                    break
        
        return results

class BotInstance:
    """Класс для управления экземпляром бота"""
    
    def __init__(self, name, config_path, script_path):
        """
        Инициализация экземпляра бота
        
        Args:
            name: Имя бота для логирования
            config_path: Путь к файлу конфигурации
            script_path: Путь к скрипту запуска бота
        """
        self.name = name
        self.config_path = config_path
        self.script_path = script_path
        self.last_hash = self.get_file_hash()
        self.process = None
        self.telegram_api = None
        self.last_api_check = 0
        self.api_check_interval = 60  # Проверять API каждую минуту
        
        # Загружаем токен бота из конфигурации
        self.load_token()
    
    def load_token(self):
        """Загружает токен бота из конфигурации"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    token = config.get("bot_token")
                    if token:
                        self.telegram_api = TelegramAPI(token)
                        logger.info(f"Токен бота '{self.name}' успешно загружен из конфигурации")
                    else:
                        logger.warning(f"Токен бота '{self.name}' не найден в конфигурации")
            else:
                logger.error(f"Файл конфигурации не найден: {self.config_path}")
        except Exception as e:
            logger.error(f"Ошибка при загрузке токена бота '{self.name}': {e}")
    
    def get_file_hash(self):
        """Вычисляет хеш-сумму файла конфигурации"""
        try:
            with open(self.config_path, 'rb') as f:
                content = f.read()
                return hashlib.md5(content).hexdigest()
        except Exception as e:
            logger.error(f"Ошибка при вычислении хеш-суммы файла {self.config_path}: {e}")
            return None
    
    def check_config_changed(self):
        """Проверяет, изменился ли файл конфигурации"""
        current_hash = self.get_file_hash()
        if current_hash is None:
            return False
        
        if self.last_hash != current_hash:
            logger.info(f"Обнаружены изменения в конфигурационном файле {self.config_path} для бота '{self.name}'")
            self.last_hash = current_hash
            # Перезагружаем токен, если файл изменился
            self.load_token()
            return True
        
        return False
    
    def validate_json(self):
        """Проверяет валидность JSON файла конфигурации"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                json.load(f)
            return True
        except json.JSONDecodeError as e:
            logger.error(f"Некорректный JSON в файле {self.config_path} для бота '{self.name}': {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка при чтении файла {self.config_path} для бота '{self.name}': {e}")
            return False
    
    def load_config(self):
        """Загружает конфигурацию из файла"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка при загрузке конфигурации бота '{self.name}': {e}")
            return None
    
    def check_api_settings(self):
        """
        Проверяет настройки бота через API Telegram и возвращает их, если они не соответствуют конфигурации
        
        Returns:
            True, если были обнаружены изменения и применены наши настройки
            False, если изменений не было или не удалось применить настройки
        """
        current_time = time.time()
        # Проверяем API не чаще, чем раз в X секунд
        if current_time - self.last_api_check < self.api_check_interval:
            return False
        
        self.last_api_check = current_time
        
        if not self.telegram_api:
            logger.warning(f"Не удалось проверить настройки бота '{self.name}' через API: API не инициализирован")
            return False
        
        # Загружаем конфигурацию
        config = self.load_config()
        if not config:
            return False
        
        # Проверяем соответствие настроек
        settings_check = self.telegram_api.check_bot_settings(config)
        
        # Если настройки не соответствуют, применяем наши настройки
        needs_update = False
        for field, is_matching in settings_check.items():
            if not is_matching:
                needs_update = True
                break
        
        if needs_update:
            logger.warning(f"Обнаружены внешние изменения настроек бота '{self.name}' в Telegram! Восстанавливаем наши настройки...")
            
            # Записываем информацию об инциденте в отдельный лог
            self.log_api_change_incident()
            
            # Применяем наши настройки
            results = self.telegram_api.apply_bot_settings(config)
            
            # Проверяем, удалось ли применить хотя бы часть настроек
            applied = False
            for field, success in results.items():
                if success:
                    applied = True
                    break
            
            if applied:
                logger.info(f"Наши настройки успешно применены к боту '{self.name}' в Telegram")
                return True
            else:
                logger.error(f"Не удалось применить наши настройки к боту '{self.name}' в Telegram")
        
        return False
    
    def log_api_change_incident(self):
        """Записывает информацию о внешнем изменении настроек бота в отдельный лог"""
        try:
            incident_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Получаем информацию о боте
            bot_info = self.telegram_api.get_bot_info() if self.telegram_api else {}
            bot_name = bot_info.get("first_name", "Неизвестно") if bot_info else "Не удалось получить"
            
            # Проверяем, есть ли webhook
            webhook_info = self.telegram_api.get_webhook_info() if self.telegram_api else {}
            webhook_url = webhook_info.get("url", "Не установлен") if webhook_info else "Не удалось получить"
            
            incident_info = (
                f"=== ИНЦИДЕНТ: ВНЕШНЕЕ ИЗМЕНЕНИЕ НАСТРОЕК БОТА '{self.name.upper()}' ===\n"
                f"Время: {incident_time}\n"
                f"Текущее имя бота: {bot_name}\n"
                f"Webhook URL: {webhook_url}\n"
                f"=============================================\n"
            )
            
            # Записываем в специальный лог
            with open("security_incidents.log", "a", encoding="utf-8") as f:
                f.write(incident_info)
            
            logger.warning(f"Зафиксирован инцидент безопасности: внешнее изменение настроек бота '{self.name}'. Подробности в security_incidents.log")
        except Exception as e:
            logger.error(f"Ошибка при логировании инцидента для бота '{self.name}': {e}")
    
    def start(self):
        """Запускает процесс бота"""
        try:
            # Проверяем валидность JSON перед запуском
            if not self.validate_json():
                logger.error(f"Бот '{self.name}' не будет запущен из-за ошибок в конфигурационном файле")
                return False
            
            # Запускаем бота в новом процессе
            logger.info(f"Запуск бота '{self.name}': {self.script_path}")
            
            # Определяем интерпретатор Python для запуска
            python_executable = sys.executable
            if not python_executable:
                python_executable = 'python'  # Или python3, в зависимости от системы
            
            # Запускаем процесс
            self.process = subprocess.Popen(
                [python_executable, self.script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
            
            logger.info(f"Бот '{self.name}' запущен, PID: {self.process.pid}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при запуске бота '{self.name}': {e}")
            return False
    
    def stop(self):
        """Останавливает процесс бота"""
        if self.process and self.process.poll() is None:
            try:
                logger.info(f"Остановка бота '{self.name}' (PID: {self.process.pid})...")
                
                # Сначала пытаемся завершить процесс корректно через SIGTERM
                self.process.send_signal(signal.SIGTERM)
                
                # Ждем завершения процесса с тайм-аутом
                timeout = 5  # секунд
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if self.process.poll() is not None:
                        logger.info(f"Бот '{self.name}' успешно остановлен")
                        return True
                    time.sleep(0.1)
                
                # Если процесс не завершился, принудительно завершаем
                logger.warning(f"Бот '{self.name}' не ответил на SIGTERM, принудительно завершаем процесс")
                self.process.kill()
                return True
            except Exception as e:
                logger.error(f"Ошибка при остановке бота '{self.name}': {e}")
                return False
        else:
            logger.info(f"Бот '{self.name}' уже остановлен или не был запущен")
            return True
    
    def restart(self):
        """Перезапускает бота"""
        logger.info(f"Перезапуск бота '{self.name}'...")
        self.stop()
        # Небольшая пауза для корректного освобождения ресурсов
        time.sleep(2)
        return self.start()

class BotsWatcher:
    """Класс для мониторинга нескольких ботов"""
    
    def __init__(self, bot_configs):
        """
        Инициализация мониторинга
        
        Args:
            bot_configs: Список конфигураций ботов
        """
        self.bots = []
        
        # Инициализируем все боты
        for bot_config in bot_configs:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, bot_config["config_file"])
            script_path = os.path.join(base_dir, bot_config["script_file"])
            
            if not os.path.exists(config_path):
                logger.error(f"Файл конфигурации не найден: {config_path}")
                continue
            
            if not os.path.exists(script_path):
                logger.error(f"Скрипт запуска бота не найден: {script_path}")
                continue
            
            bot = BotInstance(
                name=bot_config["name"],
                config_path=config_path,
                script_path=script_path
            )
            
            self.bots.append(bot)
    
    def run(self, check_interval=10):
        """
        Запускает цикл мониторинга
        
        Args:
            check_interval: Интервал проверки изменений в секундах
        """
        logger.info(f"Запуск мониторинга для {len(self.bots)} ботов")
        
        # Запускаем все боты
        for bot in self.bots:
            bot.start()
        
        try:
            while True:
                time.sleep(check_interval)
                
                for bot in self.bots:
                    # Проверяем, не завершился ли бот неожиданно
                    if bot.process and bot.process.poll() is not None:
                        exit_code = bot.process.poll()
                        logger.warning(f"Бот '{bot.name}' неожиданно завершился с кодом {exit_code}, перезапускаем...")
                        bot.start()
                        continue
                    
                    # Проверяем изменения в конфигурации
                    local_changes = bot.check_config_changed()
                    
                    # Проверяем настройки бота через API
                    api_changes = bot.check_api_settings()
                    
                    # Если были изменения в файле или через API, перезапускаем бота
                    if local_changes or api_changes:
                        logger.info(f"Обнаружены изменения в конфигурации бота '{bot.name}', перезапускаем...")
                        bot.restart()
        
        except KeyboardInterrupt:
            logger.info("Получен сигнал завершения работы")
            for bot in self.bots:
                bot.stop()
        
        except Exception as e:
            logger.error(f"Ошибка в цикле мониторинга: {e}")
            for bot in self.bots:
                bot.stop()
            raise
        
        finally:
            logger.info("Мониторинг завершен")

def main():
    """Основная функция для запуска мониторинга"""
    # Запускаем мониторинг
    watcher = BotsWatcher(BOT_CONFIGS)
    watcher.run()

if __name__ == "__main__":
    main() 