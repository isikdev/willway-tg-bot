#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль для обработки отмены подписки
"""

import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, MessageFilter
import json

# Импорт моделей базы данных
from database.models import User, get_session
# Импорт функции для получения конфигурации
from bot.config import get_bot_config

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния диалога отмены подписки
CANCEL_REASON_1 = 'CANCEL_REASON_1'
CANCEL_REASON_2 = 'CANCEL_REASON_2'
CONFIRMATION = 'CONFIRMATION'
CANCEL_CONFIRM = 'CANCEL_CONFIRM'

# Callback данные
CANCEL_SUBSCRIPTION = "cancel_subscription"
BACK_TO_MENU = "back_to_menu"
CONFIRM_CANCEL = "confirm_cancel"

def get_cancel_subscription_keyboard():
    """Клавиатура для отмены подписки"""
    keyboard = [
        [InlineKeyboardButton("Отменить подписку", callback_data=CANCEL_SUBSCRIPTION)],
        [InlineKeyboardButton("Вернуться в меню", callback_data=BACK_TO_MENU)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_renew_subscription_keyboard():
    """Клавиатура для возобновления подписки"""
    keyboard = [
        [InlineKeyboardButton("Возобновить подписку", callback_data="renew_subscription")],
        [InlineKeyboardButton("Вернуться в меню", callback_data=BACK_TO_MENU)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_external_cancel_keyboard(user_id):
    """Клавиатура для перехода на страницу отмены подписки"""
    # Формируем URL с ID пользователя для отслеживания
    cancel_url = f"https://willway.pro/cancelmembers?user_id={user_id}"
    keyboard = [
        [InlineKeyboardButton("Отменить подписку", url=cancel_url)],
        [InlineKeyboardButton("Вернуться в меню", callback_data=BACK_TO_MENU)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_cancel_confirm_keyboard():
    """
    Создает клавиатуру для подтверждения отмены
    """
    keyboard = [
        [InlineKeyboardButton("Отменить подписку", callback_data=CANCEL_SUBSCRIPTION)],
        [InlineKeyboardButton("« Назад", callback_data=BACK_TO_MENU)]
    ]
    return InlineKeyboardMarkup(keyboard)

def start_cancellation(update: Update, context: CallbackContext):
    """
    Начало процесса отмены подписки (Шаг 1)
    """
    user_id = update.effective_user.id
    query = update.callback_query
    
    logger.info(f"[DEBUG] Начало процесса отмены подписки для пользователя {user_id}")
    
    # Инициализируем объект отмены
    context.user_data['cancellation'] = {
        'reasons': [],
        'started_at': datetime.now().isoformat(),
        'active': True
    }
    
    # Показываем предупреждение о последствиях отмены
    message = """Если ты отменишь подписку, ты больше не сможешь

- Иметь доступ к программам тренировок, медитаций, практикам
- Использовать Health-ассистента, который подбирает программу питания, разбирает анализы
- Получать ответы на свои вопросы от экспертов: тренера, нутрициолога, психолога.
- Участвовать в прямых эфирах, лекциях о здоровье и оффлайн мероприятиях

Ты уверен, что хочешь отменить подписку?

После этого у тебя больше не будет доступа ко всем материалам приложения и канала"""
    
    query.answer()
    query.edit_message_text(
        text=message,
        reply_markup=get_cancel_subscription_keyboard()
    )
    
    logger.info(f"[DEBUG] Переход к состоянию CANCEL_REASON_1 для пользователя {user_id}")
    return CANCEL_REASON_1

def process_first_reason(update: Update, context: CallbackContext):
    """
    Обработка нажатия кнопки "Отменить подписку" на первом шаге (Шаг 2)
    """
    user_id = update.effective_user.id
    query = update.callback_query
    
    logger.info(f"[DEBUG] Переход ко второму шагу отмены подписки для пользователя {user_id}")
    
    # Запрашиваем первую причину
    message = """❗️️ Подписка пока НЕ отменена❗️

Прежде, мы просто обязаны узнать причину!

Расскажи пожалуйста о своём опыте, что именно не понравилось и почему"""
    
    query.answer()
    query.edit_message_text(
        text=message,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Вернуться в меню", callback_data=BACK_TO_MENU)]])
    )
    
    logger.info(f"[DEBUG] Ожидание ввода первой причины отмены от пользователя {user_id}")
    return CANCEL_REASON_1

def collect_first_reason(update: Update, context: CallbackContext):
    """
    Сохранение первой причины отмены и переход к запросу второй причины (Шаг 3)
    """
    user_id = update.effective_user.id
    reason = update.message.text
    
    logger.info(f"[DEBUG] Собираем первую причину отмены для пользователя {user_id}: {reason}")
    
    # Сохраняем первую причину
    if 'cancellation' not in context.user_data:
        logger.info(f"[DEBUG] Инициализация объекта cancellation для пользователя {user_id}")
        context.user_data['cancellation'] = {'reasons': [], 'started_at': datetime.now().isoformat(), 'active': True}
    
    # Очищаем список причин и добавляем только первую причину
    context.user_data['cancellation']['reasons'] = [reason]
    logger.info(f"[DEBUG] Пользователь {user_id} указал первую причину отмены: {reason}. Список причин: {context.user_data['cancellation']['reasons']}")
    
    # Запрашиваем вторую причину (Шаг 3)
    message = """❗️ Подписка пока НЕ отменена❗️

Второй вопрос, скажи пожалуйста что тебе нравилось и что хорошего было в WILLWAY лично для тебя?"""
    
    update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Вернуться в меню", callback_data=BACK_TO_MENU)]])
    )
    
    logger.info(f"[DEBUG] Переход к состоянию CANCEL_REASON_2 для пользователя {user_id}")
    return CANCEL_REASON_2

def collect_second_reason(update: Update, context: CallbackContext):
    """
    Сохранение второй причины и переход к финальному подтверждению (Шаг 4)
    """
    user_id = update.effective_user.id
    reason = update.message.text
    
    logger.info(f"[DEBUG] Собираем вторую причину отмены для пользователя {user_id}: {reason}")
    
    # Добавляем вторую причину в список
    if 'cancellation' in context.user_data and 'reasons' in context.user_data['cancellation']:
        context.user_data['cancellation']['reasons'].append(reason)
        logger.info(f"[DEBUG] Пользователь {user_id} указал вторую причину отмены: {reason}. Список причин: {context.user_data['cancellation']['reasons']}")
    else:
        logger.warning(f"[WARNING] Не найден объект cancellation для пользователя {user_id}. Создаем новый.")
        context.user_data['cancellation'] = {'reasons': [reason], 'started_at': datetime.now().isoformat(), 'active': True}
    
    # Сохраняем причины в базу данных
    try:
        save_cancellation_reasons(user_id, context.user_data['cancellation']['reasons'])
    except Exception as e:
        logger.error(f"[ERROR] Ошибка при сохранении причин отмены для пользователя {user_id}: {str(e)}")
    
    # Переходим к финальному подтверждению (Шаг 4)
    message = """❗️ Подписка пока НЕ отменена❗️

Благодарю за ответы!

Итак, ты уверен(а), что хочешь отменить подписку?

Отменить действие будет невозможно."""
    
    # Получаем URL для отмены подписки
    config = get_bot_config()
    cancel_url = f"{config['cancel_subscription_url']}?user_id={user_id}"
    
    # Создаем клавиатуру с кнопкой отмены (ссылка) и кнопкой возврата в меню
    keyboard = [
        [InlineKeyboardButton("Отменить подписку", url=cancel_url)],
        [InlineKeyboardButton("Вернуться в меню", callback_data=BACK_TO_MENU)]
    ]
    
    update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    logger.info(f"[DEBUG] Переход к финальному этапу отмены подписки для пользователя {user_id}")
    return CANCEL_CONFIRM

def confirm_cancellation(update: Update, context: CallbackContext):
    """
    Подтверждение отмены подписки
    """
    user_id = update.effective_user.id
    logger.info(f"[DEBUG] Подтверждение отмены подписки для пользователя {user_id}")
    
    # Проверяем наличие данных об отмене
    if 'cancellation' not in context.user_data or not context.user_data['cancellation'].get('active', False):
        logger.error(f"[ERROR] Данные об отмене не найдены для пользователя {user_id}")
        update.callback_query.answer("Произошла ошибка. Пожалуйста, попробуйте снова.")
        return ConversationHandler.END
    
    # Получаем причины отмены
    reasons = context.user_data['cancellation'].get('reasons', [])
    
    if len(reasons) < 2:
        logger.warning(f"[WARNING] Недостаточно причин отмены для пользователя {user_id}. Причины: {reasons}")
        # Если причин недостаточно, добавляем пустые
        while len(reasons) < 2:
            reasons.append("Не указана")
    
    logger.info(f"[DEBUG] Причины отмены для пользователя {user_id}: {reasons}")
    
    # Сохраняем причины в базу данных
    try:
        save_cancellation_reasons(user_id, reasons)
        logger.info(f"[DEBUG] Причины отмены сохранены для пользователя {user_id}")
    except Exception as e:
        logger.error(f"[ERROR] Ошибка при сохранении причин отмены для пользователя {user_id}: {str(e)}")
    
    # Отправляем пользователя на страницу подтверждения отмены
    config = get_bot_config()
    cancel_url = f"{config['cancel_subscription_url']}?user_id={user_id}"
    
    logger.info(f"[DEBUG] URL отмены подписки для пользователя {user_id}: {cancel_url}")
    
    message = f"""Подписка пока НЕ отменена

Для завершения отмены перейдите по ссылке: {cancel_url}"""
    
    update.callback_query.edit_message_text(
        text=message,
        reply_markup=None
    )
    
    # Завершаем диалог отмены
    context.user_data['cancellation']['active'] = False
    logger.info(f"[DEBUG] Диалог отмены завершен для пользователя {user_id}")
    
    return ConversationHandler.END

def save_cancellation_reasons(user_id, reasons):
    """
    Сохранение причин отмены подписки в базу данных
    """
    try:
        session = get_session()
        user = session.query(User).filter(User.user_id == str(user_id)).first()
        
        if user:
            logger.info(f"[DEBUG] Пытаемся сохранить причины отмены для пользователя {user_id}: {reasons}")
            try:
                # Сохраняем причины в соответствующие поля
                user.cancellation_reason_1 = reasons[0] if len(reasons) > 0 else "Не указана"
                user.cancellation_reason_2 = reasons[1] if len(reasons) > 1 else "Не указана"
                user.cancellation_date = datetime.now()
                
                logger.info(f"[DEBUG] Установлены значения в объект user: reason1={user.cancellation_reason_1}, reason2={user.cancellation_reason_2}")
                
                # Сохраняем изменения в БД
                session.commit()
                logger.info(f"Причины отмены подписки для пользователя {user_id} сохранены в БД: {reasons}")
            except Exception as e:
                # Выводим более подробную информацию об ошибке
                logger.error(f"Не удалось сохранить причины в БД: {e}")
                logger.error(f"Тип ошибки: {type(e).__name__}")
                import traceback
                logger.error(f"Стек вызовов: {traceback.format_exc()}")
                logger.info(f"Причины отмены подписки для пользователя {user_id} (только логирование): {reasons}")
                session.rollback()
                
                # Пробуем запустить миграцию напрямую
                try:
                    from migrate_cancellation import migrate_cancellation_columns
                    migrate_result = migrate_cancellation_columns()
                    logger.info(f"Результат выполнения миграции cancellation_columns: {migrate_result}")
                    
                    if migrate_result:
                        # Пробуем сохранить снова после успешной миграции
                        user.cancellation_reason_1 = reasons[0] if len(reasons) > 0 else "Не указана"
                        user.cancellation_reason_2 = reasons[1] if len(reasons) > 1 else "Не указана"
                        user.cancellation_date = datetime.now()
                        session.commit()
                        logger.info(f"Причины отмены подписки для пользователя {user_id} сохранены в БД после миграции: {reasons}")
                except Exception as migration_e:
                    logger.error(f"Ошибка при попытке выполнить миграцию: {migration_e}")
        else:
            logger.warning(f"Пользователь {user_id} не найден в базе данных")
    except Exception as e:
        logger.error(f"Ошибка при сохранении причин отмены: {e}")
    finally:
        session.close()

def back_to_menu(update, context):
    query = update.callback_query
    query.answer()
    
    from bot.handlers import show_menu
    return show_menu(update, context)

def process_subscription_webhook(data, bot=None, task_id=None):
    """
    Обработка вебхука от страницы отмены подписки
    """
    try:
        if 'user_id' not in data:
            return {"error": "user_id is required"}, 400
            
        # Получаем user_id и возможные причины отмены
        user_id = data.get('user_id')
        cancellation_info = data.get('cancellation_info', {})
        
        # Логгирование полученных данных
        logger.info(f"Получены данные для отмены подписки: user_id={user_id}, cancellation_info={cancellation_info}")
        
        # Получаем сессию БД
        session = get_session()
        
        try:
            # Находим пользователя
            user = session.query(User).filter(User.user_id == str(user_id)).first()
            
            if not user:
                logger.warning(f"Пользователь {user_id} не найден при обработке вебхука отмены подписки")
                session.close()
                return {"error": "User not found"}, 404
                
            # Сохраняем информацию об отмене
            user.cancellation_date = datetime.now()
            
            # Сохраняем причины отмены в метаданных
            try:
                metadata = json.loads(user.metadata) if user.metadata else {}
            except:
                metadata = {}
                
            # Устанавливаем флаг запроса на отмену
            metadata['is_cancellation_requested'] = True
            
            # Сохраняем причины отмены
            if cancellation_info:
                metadata['cancellation_info'] = cancellation_info
                
            # Сохраняем метаданные
            user.metadata = json.dumps(metadata)
            session.commit()
            
            logger.info(f"Установлен флаг отмены подписки для пользователя {user_id}")
            
            # Проверяем, было ли уже отправлено сообщение
            message_already_sent = False
            if metadata.get('cancellation_message_sent', False):
                message_already_sent = True
                logger.info(f"Сообщение об отмене подписки уже было отправлено пользователю {user_id}")
            
            # Если сообщение ещё не отправлялось и бот доступен, отправляем уведомление
            if not message_already_sent and bot:
                try:
                    # Проверяем наличие job_queue у бота
                    if hasattr(bot, 'job_queue') and bot.job_queue:
                        # Планируем отправку сообщения через определенное время
                        bot.job_queue.run_once(
                            check_subscription_cancellation,
                            5,  # Задержка в секундах
                            context={'user_id': user_id}
                        )
                        logger.info(f"Запланирована отправка уведомления об отмене подписки для пользователя {user_id}")
                    else:
                        # Если job_queue недоступен, отправляем сообщение напрямую
                        # Форматируем дату окончания подписки
                        expiry_date = user.subscription_expires.strftime("%d.%m.%Y") if user.subscription_expires else "неизвестной даты"
                        
                        message = f"""Статус подписки WILLWAY
🔴 Отменена

Доступ к приложению и каналу сохранится до {expiry_date}

Возобнови подписку, чтобы сохранить доступ"""
                        
                        # Отправляем сообщение напрямую
                        bot.send_message(
                            chat_id=user_id,
                            text=message,
                            reply_markup=get_renew_subscription_keyboard()
                        )
                        
                        # Помечаем, что сообщение отправлено
                        metadata['cancellation_message_sent'] = True
                        user.metadata = json.dumps(metadata)
                        session.commit()
                        
                        logger.info(f"Отправлено прямое уведомление об отмене подписки пользователю {user_id}")
                except Exception as e:
                    logger.error(f"Ошибка при отправке уведомления: {e}")
            else:
                logger.info(f"Уведомление не отправлено: message_already_sent={message_already_sent}, bot={'доступен' if bot else 'недоступен'}")
                
            # Добавляем задачу в очередь через RQ, если это задача из очереди
            if task_id:
                logger.info(f"Задача {task_id} - Отмена подписки для пользователя {user_id} завершена")
                
            return {"status": "success"}, 200
        except Exception as e:
            logger.error(f"Ошибка при обработке запроса отмены подписки: {e}")
            session.rollback()
            return {"error": str(e)}, 500
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Необработанная ошибка в process_subscription_webhook: {e}")
        return {"error": str(e)}, 500

def check_subscription_cancellation(context: CallbackContext):
    """
    Проверка статуса отмены подписки и отправка уведомления
    """
    job = context.job
    user_id = job.context['user_id']
    
    try:
        session = get_session()
        user = session.query(User).filter(User.user_id == str(user_id)).first()
        
        if not user:
            logger.warning(f"Пользователь {user_id} не найден при проверке статуса отмены подписки")
            session.close()
            return
            
        # Проверяем, было ли уже отправлено сообщение об отмене
        message_already_sent = False
        if hasattr(user, 'metadata') and user.metadata:
            try:
                metadata = json.loads(user.metadata) if isinstance(user.metadata, str) else user.metadata
                message_already_sent = metadata.get('cancellation_message_sent', False)
                logger.info(f"Проверка отправки сообщения для пользователя {user_id}: message_already_sent={message_already_sent}")
            except Exception as e:
                logger.warning(f"Не удалось проверить статус отправки сообщения в метаданных: {e}")
            
        # Если сообщение уже было отправлено, завершаем обработку
        if message_already_sent:
            logger.info(f"Сообщение об отмене подписки уже было отправлено пользователю {user_id}, пропускаем повторную отправку")
            session.close()
            return
            
        # Проверяем наличие флага отмены подписки
        is_cancellation_requested = False
        
        # Проверяем прямой атрибут
        if hasattr(user, 'is_cancellation_requested'):
            is_cancellation_requested = user.is_cancellation_requested
        # Проверяем в метаданных
        elif hasattr(user, 'metadata') and user.metadata:
            try:
                metadata = json.loads(user.metadata) if isinstance(user.metadata, str) else user.metadata
                is_cancellation_requested = metadata.get('is_cancellation_requested', False)
            except Exception as e:
                logger.warning(f"Не удалось прочитать метаданные пользователя {user_id}: {e}")
                
        # Также проверяем наличие даты отмены
        has_cancellation_date = hasattr(user, 'cancellation_date') and user.cancellation_date is not None
        
        # Если запрошена отмена подписки или есть дата отмены, отправляем уведомление
        if is_cancellation_requested or has_cancellation_date:
            # Форматируем дату окончания подписки
            expiry_date = user.subscription_expires.strftime("%d.%m.%Y") if user.subscription_expires else "неизвестной даты"
            
            message = f"""Статус подписки WILLWAY
🔴 Отменена

Доступ к приложению и каналу сохранится до {expiry_date}

Возобнови подписку, чтобы сохранить доступ"""
            
            try:
                # Отправляем уведомление
                context.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    reply_markup=get_renew_subscription_keyboard()
                )
                logger.info(f"Отправлено уведомление об отмене подписки пользователю {user_id}")
                
                # Устанавливаем флаг, что сообщение отправлено
                try:
                    metadata = json.loads(user.metadata) if user.metadata else {}
                    metadata['cancellation_message_sent'] = True
                    user.metadata = json.dumps(metadata)
                    session.commit()
                    logger.info(f"Установлен флаг отправки сообщения об отмене для пользователя {user_id}")
                except Exception as e:
                    logger.warning(f"Не удалось обновить метаданные пользователя для отметки отправки сообщения: {e}")
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления: {e}")
        else:
            logger.info(f"Подписка пользователя {user_id} не отменена")
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса отмены подписки: {e}")
    finally:
        session.close()

# Создаем фильтр для сообщений отмены подписки
class CancellationFilter(MessageFilter):
    def filter(self, message):
        # Проверяем, есть ли объект context в обработчике
        if not hasattr(self, 'context'):
            return False
        
        # Получаем user_id и проверяем, активен ли процесс отмены
        user_id = message.from_user.id
        user_data = self.context.user_data.get(user_id, {})
        active = 'cancellation' in user_data
        
        if active:
            logging.info(f"[CANCELLATION_FILTER] Сообщение от {user_id} перехвачено фильтром отмены подписки")
        
        return active

# Создаем экземпляр фильтра
cancellation_filter = CancellationFilter()

def setup_cancellation_filter(context):
    """Устанавливает контекст для фильтра отмены подписки"""
    cancellation_filter.context = context

# Функция для маршрутизации сообщений отмены подписки
def route_cancellation_message(update: Update, context: CallbackContext):
    """
    Маршрутизация сообщения на основе текущего шага отмены
    """
    user_id = update.effective_user.id
    message_text = update.message.text
    
    logger.info(f"[DEBUG] Маршрутизация сообщения от пользователя {user_id}: '{message_text}'")
    
    # Инициализируем объект отмены, если его нет
    if 'cancellation' not in context.user_data:
        logger.info(f"[DEBUG] Инициализация объекта cancellation в маршрутизаторе для пользователя {user_id}")
        context.user_data['cancellation'] = {
            'reasons': [], 
            'started_at': datetime.now().isoformat(),
            'active': True
        }
    
    # Определяем текущий шаг на основе количества уже собранных причин
    reasons_count = len(context.user_data['cancellation'].get('reasons', []))
    
    logger.info(f"[DEBUG] Количество собранных причин: {reasons_count}, причины: {context.user_data['cancellation'].get('reasons', [])}")
    
    # Маршрутизация на основе количества причин
    if reasons_count == 0:
        # Шаг 2 - сбор первой причины
        logger.info(f"[DEBUG] Маршрутизация для первой причины отмены для пользователя {user_id}")
        return collect_first_reason(update, context)
    elif reasons_count == 1:
        # Шаг 3 - сбор второй причины
        logger.info(f"[DEBUG] Маршрутизация для второй причины отмены для пользователя {user_id}")
        return collect_second_reason(update, context)
    else:
        # Шаг 4 - уже собраны все причины, переходим к финальному шагу
        logger.info(f"[DEBUG] Обе причины уже собраны, сохраняем дополнительный комментарий для пользователя {user_id}")
        
        # Если пользователь отправил еще текст, сохраняем его как дополнительный комментарий
        if len(context.user_data['cancellation'].get('reasons', [])) >= 2:
            context.user_data['cancellation']['additional_comment'] = message_text
            logger.info(f"[DEBUG] Сохранен дополнительный комментарий в контексте: {message_text}")
            
            # Сохраняем дополнительный комментарий в базе данных
            try:
                save_additional_comment(user_id, message_text)
            except Exception as e:
                logger.error(f"[ERROR] Ошибка при сохранении дополнительного комментария: {e}")
        
        # Получаем URL для отмены
        config = get_bot_config()
        cancel_url = f"{config['cancel_subscription_url']}?user_id={user_id}"
        
        message = """❗️ Подписка пока НЕ отменена❗️

Благодарю за ответы!

Итак, ты уверен(а), что хочешь отменить подписку?

Отменить действие будет невозможно."""
        
        # Создаем клавиатуру с кнопкой отмены (ссылка) и кнопкой возврата в меню
        keyboard = [
            [InlineKeyboardButton("Отменить подписку", url=cancel_url)],
            [InlineKeyboardButton("Вернуться в меню", callback_data=BACK_TO_MENU)]
        ]
        
        update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return CANCEL_CONFIRM

def setup_subscription_cancel_handlers(dispatcher):
    """
    Настройка обработчиков для отмены подписки
    """
    # Устанавливаем контекст для фильтра отмены подписки
    setup_cancellation_filter(dispatcher)
    
    # Обработчики для процесса отмены подписки
    cancel_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_cancellation, pattern=f'^{CANCEL_SUBSCRIPTION}$'),
            CallbackQueryHandler(start_cancellation, pattern='^cancel_subscription_start$')
        ],
        states={
            CANCEL_REASON_1: [
                # Для первого шага - либо обработка нажатия на кнопку "Отменить подписку", 
                # либо получение текста первой причины
                CallbackQueryHandler(process_first_reason, pattern=f'^{CANCEL_SUBSCRIPTION}$'),
                MessageHandler(CancellationFilter(), collect_first_reason),
                CallbackQueryHandler(back_to_menu, pattern=f'^{BACK_TO_MENU}$')
            ],
            CANCEL_REASON_2: [
                # Для второго шага - получение текста второй причины
                MessageHandler(CancellationFilter(), collect_second_reason),
                CallbackQueryHandler(back_to_menu, pattern=f'^{BACK_TO_MENU}$')
            ],
            CANCEL_CONFIRM: [
                # Для финального шага - только возврат в меню
                CallbackQueryHandler(back_to_menu, pattern=f'^{BACK_TO_MENU}$')
            ]
        },
        fallbacks=[
            CallbackQueryHandler(back_to_menu, pattern=f'^{BACK_TO_MENU}$')
        ],
        name="subscription_cancellation",
        persistent=False
    )
    
    # Добавляем обработчик в диспетчер
    dispatcher.add_handler(cancel_handler)
    
    # Добавляем отдельный высокоприоритетный обработчик для текстовых сообщений в процессе отмены
    dispatcher.add_handler(
        MessageHandler(Filters.text & ~Filters.command & cancellation_filter, 
                      route_cancellation_message),
        group=-2  # Высокий приоритет, чем у обработчика обратной связи
    )
    
    # Добавляем отдельный обработчик для кнопки возобновления подписки
    dispatcher.add_handler(CallbackQueryHandler(
        lambda update, context: show_subscription_options(update, context),
        pattern='^renew_subscription$'
    ))
    
    logger.info("Обработчики отмены подписки успешно настроены")

def get_cancel_subscription_button():
    """
    Получение кнопки для отмены подписки (для использования в других модулях)
    """
    return InlineKeyboardButton("Отменить подписку", callback_data="cancel_subscription_start")

def show_subscription_options(update: Update, context: CallbackContext):
    """
    Показать опции подписки для возобновления
    """
    query = update.callback_query
    query.answer()
    
    # Переадресация на функцию отображения вариантов подписки из основного модуля
    # Здесь должна быть ссылка на функцию из handlers.py
    try:
        from bot.handlers import handle_show_subscription_options
        return handle_show_subscription_options(update, context)
    except ImportError:
        logger.error("Не удалось импортировать функцию handle_show_subscription_options")
        query.message.reply_text(
            "Пожалуйста, свяжитесь с поддержкой для возобновления подписки.",
            reply_markup=get_cancel_subscription_keyboard()
        )

def show_subscription_management(update: Update, context: CallbackContext):
    """
    Показывает информацию о подписке и кнопку отмены (Шаг 0)
    """
    user_id = update.effective_user.id
    logger.info(f"[DEBUG] Показ информации о подписке для пользователя {user_id}")
    
    # Получаем информацию о подписке пользователя
    try:
        session = get_session()
        user = session.query(User).filter(User.user_id == str(user_id)).first()
        
        if user:
            # Определяем тип подписки
            subscription_type = "Месячная" if user.subscription_type == "monthly" else "Годовая"
            
            # Форматируем дату окончания подписки
            expiry_date = user.subscription_expires.strftime("%d.%m.%Y") if user.subscription_expires else "Не указано"
            
            # Проверяем, была ли запрошена отмена подписки
            is_cancellation_requested = False
            
            # Проверяем прямой атрибут
            if hasattr(user, 'is_cancellation_requested'):
                is_cancellation_requested = user.is_cancellation_requested
            # Проверяем в метаданных
            elif hasattr(user, 'metadata') and user.metadata:
                try:
                    metadata = json.loads(user.metadata) if isinstance(user.metadata, str) else user.metadata
                    is_cancellation_requested = metadata.get('is_cancellation_requested', False)
                except:
                    logger.warning(f"Не удалось прочитать метаданные пользователя {user_id}")
                    
            # Также проверяем наличие даты отмены
            has_cancellation_date = hasattr(user, 'cancellation_date') and user.cancellation_date is not None
            
            # Расчет оставшихся дней
            days_left = 0
            if user.subscription_expires:
                from datetime import datetime
                now = datetime.now()
                delta = user.subscription_expires - now
                days_left = max(0, delta.days)
            
            # Если подписка активна
            if user.is_subscribed:
                # Определяем статус подписки и сообщение в зависимости от статуса отмены
                if is_cancellation_requested or has_cancellation_date:
                    # Если подписка была отменена (автопродление отключено)
                    message = f"""💎 Информация о подписке

• Тип: {subscription_type.lower()}
• Активна до: {expiry_date}
• Осталось дней: {days_left}

Автоматическое продление отключено.
Доступ к сервису сохранится до окончания оплаченного периода."""

                    # Клавиатура для возобновления подписки
                    keyboard = [
                        [InlineKeyboardButton("Возобновить подписку", callback_data="renew_subscription")],
                        [InlineKeyboardButton("« Назад", callback_data=BACK_TO_MENU)]
                    ]
                else:
                    # Если подписка активна и не отменена
                    message = f"""💎 Информация о подписке

• Тип: {subscription_type.lower()}
• Активна до: {expiry_date}
• Осталось дней: {days_left}

Для отключения автопродления нажмите кнопку ниже."""

                    # Клавиатура с кнопкой отмены
                    keyboard = [
                        [InlineKeyboardButton("Отключить автопродление", callback_data="cancel_subscription_start")],
                        [InlineKeyboardButton("« Назад", callback_data=BACK_TO_MENU)]
                    ]
            else:
                # Если подписка неактивна
                message = f"""💎 Информация о подписке

В данный момент у вас нет активной подписки.
Для получения доступа к премиум-возможностям оформите подписку."""

                # Клавиатура для оформления подписки
                keyboard = [
                    [InlineKeyboardButton("Оформить подписку", callback_data="show_subscription_options")],
                    [InlineKeyboardButton("« Назад", callback_data=BACK_TO_MENU)]
                ]
            
            # Отправляем сообщение
            if update.callback_query:
                # Если вызвано из callback query
                query = update.callback_query
                query.answer()
                query.edit_message_text(
                    text=message,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                # Если вызвано из текстового сообщения
                update.message.reply_text(
                    message,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            
            logger.info(f"[DEBUG] Информация о подписке показана пользователю {user_id}")
        else:
            # Если пользователь не найден в базе данных
            error_message = "Информация о подписке недоступна. Пожалуйста, обратитесь в поддержку."
            
            if update.callback_query:
                query = update.callback_query
                query.answer()
                query.edit_message_text(
                    text=error_message,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data=BACK_TO_MENU)]])
                )
            else:
                update.message.reply_text(
                    error_message,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data=BACK_TO_MENU)]])
                )
            
            logger.warning(f"[WARNING] Пользователь {user_id} не найден в базе данных при попытке показать информацию о подписке")
    except Exception as e:
        logger.error(f"[ERROR] Ошибка при отображении информации о подписке для пользователя {user_id}: {e}")
        
        error_message = "Произошла ошибка при получении информации о подписке. Пожалуйста, попробуйте позже."
        
        if update.callback_query:
            query = update.callback_query
            query.answer()
            query.edit_message_text(
                text=error_message,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data=BACK_TO_MENU)]])
            )
        else:
            update.message.reply_text(
                error_message,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data=BACK_TO_MENU)]])
            )
    finally:
        session.close()
    
    return ConversationHandler.END

def save_additional_comment(user_id, comment):
    """
    Сохраняет дополнительный комментарий к отмене подписки
    """
    try:
        session = get_session()
        user = session.query(User).filter(User.user_id == str(user_id)).first()
        
        if user:
            # Сохраняем дополнительный комментарий
            # Если у нас нет специального поля, добавляем его к одной из причин
            if hasattr(user, 'cancellation_additional_comment'):
                user.cancellation_additional_comment = comment
            else:
                # Если нет специального поля, добавляем к существующей причине
                if user.cancellation_reason_2:
                    user.cancellation_reason_2 = f"{user.cancellation_reason_2}\n--- Дополнительно: {comment}"
                else:
                    user.cancellation_reason_2 = f"Дополнительно: {comment}"
            
            # Сохраняем изменения
            session.commit()
            logger.info(f"Дополнительный комментарий для пользователя {user_id} сохранен: {comment}")
            return True
        else:
            logger.warning(f"Пользователь {user_id} не найден для сохранения дополнительного комментария")
            return False
    except Exception as e:
        logger.error(f"Ошибка при сохранении дополнительного комментария: {e}")
        return False
    finally:
        session.close()

# Экспортируем важные функции для использования в других модулях
__all__ = [
    'setup_subscription_cancel_handlers',
    'get_cancel_subscription_button',
    'show_subscription_management',
    'process_subscription_webhook',
    'save_cancellation_reasons',
    'save_additional_comment',
    'check_subscription_cancellation'
] 