#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль для обновления настроек бота через API Telegram с использованием aiogram
"""

import logging
import json
import os
import asyncio
import aiohttp
from typing import Dict, Any, Optional, List

# Настройка логирования
logger = logging.getLogger(__name__)

class BotUpdater:
    """Класс для обновления настроек бота через API Telegram"""
    
    def __init__(self, token: str):
        """
        Инициализация класса
        
        Args:
            token: Токен бота Telegram
        """
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        
    async def update_bot_settings(self, config: Dict[str, Any]) -> Dict[str, bool]:
        """
        Обновляет настройки бота через API Telegram
        
        Args:
            config: Конфигурация бота
            
        Returns:
            Словарь с результатами обновления
        """
        results = {
            "name": False,
            "description": False,
            "about": False,
            "commands": False,
            "profile_photo": False
        }
        
        # Сессия для запросов к API
        async with aiohttp.ClientSession() as session:
            # Обновление имени бота
            if "bot_name" in config:
                name_result = await self._update_bot_name(session, config["bot_name"])
                results["name"] = name_result
            
            # Обновление описания бота
            if "description" in config:
                desc_result = await self._update_bot_description(session, config["description"])
                results["description"] = desc_result
            
            # Обновление "О боте" 
            if "about_text" in config:
                about_result = await self._update_bot_about(session, config["about_text"])
                results["about"] = about_result
            
            # Обновление команд бота
            if "commands" in config and isinstance(config["commands"], dict):
                commands_result = await self._update_bot_commands(session, config["commands"])
                results["commands"] = commands_result
            
            # Обновление аватара бота
            if "botpic_url" in config and config["botpic_url"]:
                # Проверяем, что это локальный путь к файлу
                photo_path = config.get("botpic_absolute_path") or config["botpic_url"]
                if os.path.exists(photo_path):
                    photo_result = await self._update_profile_photo(session, photo_path)
                    results["profile_photo"] = photo_result
        
        return results
    
    async def _update_bot_name(self, session: aiohttp.ClientSession, name: str) -> bool:
        """Обновляет имя бота"""
        try:
            async with session.post(f"{self.api_url}/setMyName", data={"name": name}) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info(f"Имя бота успешно обновлено на: {name}")
                        return True
                    else:
                        logger.error(f"Ошибка при обновлении имени бота: {result.get('description')}")
                else:
                    logger.error(f"Ошибка HTTP при обновлении имени бота: {response.status}")
        except Exception as e:
            logger.error(f"Исключение при обновлении имени бота: {e}")
        return False
    
    async def _update_bot_description(self, session: aiohttp.ClientSession, description: str) -> bool:
        """Обновляет описание бота"""
        try:
            async with session.post(f"{self.api_url}/setMyDescription", data={"description": description}) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info(f"Описание бота успешно обновлено")
                        return True
                    else:
                        logger.error(f"Ошибка при обновлении описания бота: {result.get('description')}")
                else:
                    logger.error(f"Ошибка HTTP при обновлении описания бота: {response.status}")
        except Exception as e:
            logger.error(f"Исключение при обновлении описания бота: {e}")
        return False
    
    async def _update_bot_about(self, session: aiohttp.ClientSession, about: str) -> bool:
        """Обновляет информацию "О боте" """
        try:
            async with session.post(f"{self.api_url}/setMyShortDescription", data={"short_description": about}) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info(f"Информация 'О боте' успешно обновлена")
                        return True
                    else:
                        logger.error(f"Ошибка при обновлении информации 'О боте': {result.get('description')}")
                else:
                    logger.error(f"Ошибка HTTP при обновлении информации 'О боте': {response.status}")
        except Exception as e:
            logger.error(f"Исключение при обновлении информации 'О боте': {e}")
        return False
    
    async def _update_bot_commands(self, session: aiohttp.ClientSession, commands: Dict[str, str]) -> bool:
        """Обновляет команды бота"""
        try:
            # Преобразуем словарь команд в нужный формат
            formatted_commands = []
            for cmd, desc in commands.items():
                # Убираем символ "/" если он есть в начале команды
                cmd_name = cmd[1:] if cmd.startswith('/') else cmd
                formatted_commands.append({"command": cmd_name, "description": desc})
            
            data = {"commands": json.dumps(formatted_commands)}
            
            async with session.post(f"{self.api_url}/setMyCommands", data=data) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info(f"Команды бота успешно обновлены")
                        return True
                    else:
                        logger.error(f"Ошибка при обновлении команд бота: {result.get('description')}")
                else:
                    logger.error(f"Ошибка HTTP при обновлении команд бота: {response.status}")
        except Exception as e:
            logger.error(f"Исключение при обновлении команд бота: {e}")
        return False
    
    async def _update_profile_photo(self, session: aiohttp.ClientSession, photo_path: str) -> bool:
        try:
            form = aiohttp.FormData()
            form.add_field('photo', open(photo_path, 'rb'))
            
            async with session.post(f"{self.api_url}/setMyPhoto", data=form) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info(f"Аватар бота успешно обновлен")
                        return True
                    else:
                        logger.error(f"Ошибка при обновлении аватара бота: {result.get('description')}")
                else:
                    logger.error(f"Ошибка HTTP при обновлении аватара бота: {response.status}")
        except Exception as e:
            logger.error(f"Исключение при обновлении аватара бота: {e}")
        return False

async def update_bot_settings(token: str, config: Dict[str, Any]) -> Dict[str, bool]:
    updater = BotUpdater(token)
    return await updater.update_bot_settings(config)
    
def apply_bot_settings(token: str, config: Dict[str, Any]) -> Dict[str, bool]:
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        results = loop.run_until_complete(update_bot_settings(token, config))
        return results
    except Exception as e:
        logger.error(f"Ошибка при обновлении настроек бота: {e}")
        return {"error": str(e)} 