from flask import Blueprint, request, jsonify
import logging
from datetime import datetime, timedelta
import json
import os
import sys
from functools import wraps
import colorlog
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.models import get_session, User, Payment, ReferralUse, ReferralCode
from bot.handlers import get_bot_config, initialize_bot  # Импортируем функции из handlers.py
from dotenv import load_dotenv

load_dotenv()

handler = colorlog.StreamHandler()
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

payment_logger = logging.getLogger('payment_system')
payment_logger.setLevel(logging.DEBUG)
payment_logger.addHandler(handler)
payment_logger.addHandler(file_handler)

payment_bp = Blueprint('payment', __name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
payment_logger.info(f"\033[93mТокен бота получен: {'Да' if TELEGRAM_TOKEN else 'Нет'}\033[0m")
if TELEGRAM_TOKEN:
    payment_logger.info(f"\033[93mДлина токена: {len(TELEGRAM_TOKEN)} символов\033[0m")
else:
    payment_logger.error(f"\033[91mТелеграм токен отсутствует в переменных окружения! Проверьте настройки .env файла\033[0m")

try:
    payment_logger.info(f"\033[93mПытаемся инициализировать бота с полученным токеном\033[0m")
    bot = Bot(token=TELEGRAM_TOKEN)
    payment_logger.info(f"\033[92mБот успешно инициализирован\033[0m")
except Exception as e:
    payment_logger.error(f"\033[91mОшибка при инициализации бота: {str(e)}\033[0m")
    import traceback
    payment_logger.error(f"\033[91mДетали ошибки: {traceback.format_exc()}\033[0m")
    bot = None

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function

@payment_bp.route('/api/v1/payment/track', methods=['POST'])
@require_api_key
def track_payment():
    data = request.json
    payment_logger.info(f"\033[94mОтслеживание посещения страницы оплаты: {data}\033[0m")
    
    user_id = data.get('user_id')
    if not user_id:
        payment_logger.error("\033[91mНе указан user_id в запросе трекера платежа\033[0m")
        return jsonify({"status": "error", "message": "User ID is required"}), 400
    
    session = get_session()
    try:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            payment_logger.error(f"\033[91mПользователь с ID {user_id} не найден в базе данных\033[0m")
            return jsonify({"status": "error", "message": "User not found"}), 404
        
        user.payment_status = 'pending'
        session.commit()
        
        payment_logger.info(f"\033[94mСтатус платежа для пользователя {user_id} изменен на 'pending'\033[0m")
        
        return jsonify({"status": "success", "message": "Payment tracking initiated"})
    except Exception as e:
        session.rollback()
        payment_logger.error(f"\033[91mОшибка при отслеживании платежа: {str(e)}\033[0m")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        session.close()

@payment_bp.route('/api/v1/payment/success', methods=['POST'])
@require_api_key
def payment_success():
    """
    Обработчик успешной оплаты
    """
    data = request.json
    payment_logger.info(f"\033[93mДанные об успешной оплате: {data}\033[0m")
    
    user_id = data.get('user_id')
    subscription_type = data.get('subscription_type', 'monthly')
    amount = data.get('amount', 1555)  # Значение по умолчанию для месячной подписки
    
    if not user_id:
        payment_logger.error("\033[91mНе указан user_id в запросе успешной оплаты\033[0m")
        return jsonify({"status": "error", "message": "User ID is required"}), 400
    
    # Регистрируем успешную оплату
    session = get_session()
    try:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            payment_logger.error(f"\033[91mПользователь с ID {user_id} не найден в базе данных\033[0m")
            return jsonify({"status": "error", "message": "User not found"}), 404
        
        # Устанавливаем дату окончания подписки (1 месяц от текущей даты)
        subscription_expires = datetime.now() + timedelta(days=30)
        if subscription_type == 'yearly':
            subscription_expires = datetime.now() + timedelta(days=365)
        
        # Обновляем информацию о подписке пользователя
        user.is_subscribed = True
        user.subscription_type = subscription_type
        user.subscription_expires = subscription_expires
        user.payment_status = 'completed'
        
        # Создаем запись о платеже - используем только поддерживаемые поля
        payment = Payment(
            user_id=user.id,  # Используем ID из таблицы, а не Telegram ID
            payment_method='tilda',
            amount=amount,
            status='completed',
            subscription_type=subscription_type
        )
        
        # Устанавливаем дату оплаты
        payment.paid_at = datetime.now()
        
        session.add(payment)
        
        # Проверяем, был ли пользователь приглашен по реферальной ссылке
        # и начисляем бонус реферреру, если да
        if user.referrer_id:
            # Получаем реферера
            referrer = session.query(User).filter_by(user_id=user.referrer_id).first()
            payment_logger.info(f"\033[93m[REFERRAL] Обработка реферальной системы для пользователя {user_id}, приглашён пользователем {user.referrer_id}\033[0m")
            
            if referrer:
                payment_logger.info(f"\033[93m[REFERRAL] Найден рефер с ID {referrer.user_id}, имя: {referrer.username}\033[0m")
                
                # Проверяем, есть ли уже запись об использовании реферальной ссылки
                try:
                    # Сначала пробуем найти по ID из таблицы
                    ref_use = session.query(ReferralUse).filter_by(
                        referrer_id=referrer.id,
                        user_id=user.id
                    ).first()
                    
                    if not ref_use:
                        # Если не найдено, попробуем поискать по Telegram ID (для обратной совместимости)
                        ref_use = session.query(ReferralUse).filter_by(
                            referrer_id=int(user.referrer_id),
                            referred_id=int(user_id)
                        ).first()
                        
                        if ref_use and ref_use.user_id != user.id:
                            # Обновляем поле user_id, если оно не заполнено
                            ref_use.user_id = user.id
                            payment_logger.info(f"\033[93m[REFERRAL] Обновлен user_id в существующей записи использования реферальной ссылки\033[0m")
                    
                    if ref_use:
                        # Обновляем статус подписки в записи использования
                        ref_use.subscription_purchased = True
                        ref_use.purchase_date = datetime.now()
                        payment_logger.info(f"\033[93m[REFERRAL] Обновлена запись об использовании реферальной ссылки (ID {ref_use.id})\033[0m")
                        
                        # Начисляем бонус реферреру (продлеваем его подписку на 30 дней)
                        if referrer.is_subscribed and referrer.subscription_expires:
                            referrer.subscription_expires += timedelta(days=30)
                            payment_logger.info(f"\033[92m[REFERRAL_BONUS] Начислен бонус +30 дней пользователю {referrer.user_id}. Новая дата окончания: {referrer.subscription_expires}\033[0m")
                            # Отправляем уведомление о начислении бонуса
                            send_referral_bonus_notification(referrer.user_id, user.username or "Новый пользователь")
                        else:
                            # Активируем подписку, если она не активна
                            referrer.is_subscribed = True
                            referrer.subscription_type = "monthly"
                            referrer.subscription_expires = datetime.now() + timedelta(days=30)
                            payment_logger.info(f"\033[92m[REFERRAL_BONUS] Активирована бонусная подписка на 30 дней для пользователя {referrer.user_id}\033[0m")
                            # Отправляем уведомление о начислении бонуса
                            send_referral_bonus_notification(referrer.user_id, user.username or "Новый пользователь")
                    else:
                        # Создаем новую запись об использовании реферальной ссылки
                        try:
                            # Находим реферальный код пользователя
                            ref_code = session.query(ReferralCode).filter(
                                ReferralCode.user_id == referrer.id,
                                ReferralCode.is_active == True
                            ).first()
                            
                            if ref_code:
                                try:
                                    # Пробуем создать запись с новой структурой
                                    new_ref_use = ReferralUse(
                                        code_id=ref_code.id,  # Обновленное название поля
                                        user_id=user.id,
                                        referrer_id=referrer.id,
                                        subscription_purchased=True,
                                        purchase_date=datetime.now()
                                    )
                                    session.add(new_ref_use)
                                    payment_logger.info(f"\033[93m[REFERRAL] Создана новая запись использования реферальной ссылки с обновленной структурой\033[0m")
                                except Exception as new_struct_error:
                                    payment_logger.warning(f"\033[93m[REFERRAL] Ошибка при создании записи с обновленной структурой: {str(new_struct_error)}\033[0m")
                                    
                                    # Пробуем создать запись со старой структурой
                                    try:
                                        new_ref_use = ReferralUse(
                                            referral_code_id=ref_code.id,
                                            user_id=user.id,
                                            referrer_id=referrer.id,
                                            referred_id=int(user_id),  # Для обратной совместимости
                                            subscription_purchased=True,
                                            purchase_date=datetime.now()
                                        )
                                        session.add(new_ref_use)
                                        payment_logger.info(f"\033[93m[REFERRAL] Создана новая запись использования реферальной ссылки со старой структурой\033[0m")
                                    except Exception as old_struct_error:
                                        payment_logger.error(f"\033[91m[REFERRAL] Ошибка при создании записи со старой структурой: {str(old_struct_error)}\033[0m")
                                        raise old_struct_error  # Передаем ошибку дальше
                                
                                # Начисляем бонус реферреру
                                if referrer.is_subscribed and referrer.subscription_expires:
                                    referrer.subscription_expires += timedelta(days=30)
                                    payment_logger.info(f"\033[92m[REFERRAL_BONUS] Начислен бонус +30 дней пользователю {referrer.user_id}. Новая дата окончания: {referrer.subscription_expires}\033[0m")
                                    # Отправляем уведомление о начислении бонуса
                                    send_referral_bonus_notification(referrer.user_id, user.username or "Новый пользователь")
                                else:
                                    # Активируем подписку, если она не активна
                                    referrer.is_subscribed = True
                                    referrer.subscription_type = "monthly"
                                    referrer.subscription_expires = datetime.now() + timedelta(days=30)
                                    payment_logger.info(f"\033[92m[REFERRAL_BONUS] Активирована бонусная подписка на 30 дней для пользователя {referrer.user_id}\033[0m")
                                    # Отправляем уведомление о начислении бонуса
                                    send_referral_bonus_notification(referrer.user_id, user.username or "Новый пользователь")
                            else:
                                payment_logger.warning(f"\033[93m[REFERRAL] Не найден активный реферальный код для пользователя {referrer.user_id}\033[0m")
                        except Exception as ref_create_error:
                            payment_logger.error(f"\033[91m[REFERRAL] Ошибка при создании записи об использовании реферальной ссылки: {str(ref_create_error)}\033[0m")
                        
                except Exception as ref_error:
                    payment_logger.error(f"\033[91m[REFERRAL] Ошибка при обработке реферальной системы: {str(ref_error)}\033[0m")
            else:
                payment_logger.warning(f"\033[93m[REFERRAL] Реферер с ID {user.referrer_id} не найден в базе данных\033[0m")
        
        session.commit()
        payment_logger.info(f"\033[92mУспешно обновлен статус подписки для пользователя {user_id}\033[0m")
        
        # Отправляем уведомление пользователю об успешной оплате
        try:
            # Проверяем текущее значение флага welcome_message_sent
            payment_logger.info(f"\033[93mТекущее значение флага welcome_message_sent для пользователя {user_id}: {user.welcome_message_sent}\033[0m")
            
            # Отправляем сообщение в любом случае, независимо от флага welcome_message_sent
            payment_logger.info(f"\033[93mПытаемся отправить приветственное сообщение пользователю {user_id}\033[0m")
            send_success = send_success_message(user_id)
            if send_success:
                user.welcome_message_sent = True
                session.commit()
                payment_logger.info(f"\033[92mОтправлено сообщение о успешной оплате пользователю {user_id}\033[0m")
            else:
                payment_logger.warning(f"\033[93mНе удалось отправить сообщение о успешной оплате пользователю {user_id}\033[0m")
        except Exception as msg_error:
            payment_logger.error(f"\033[91mОшибка при отправке сообщения о успешной оплате: {str(msg_error)}\033[0m")
        
        return jsonify({
            "status": "success",
            "user_id": user_id,
            "subscription_type": subscription_type,
            "expires_at": subscription_expires.strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        session.rollback()
        payment_logger.error(f"\033[91mОшибка при обработке успешной оплаты: {str(e)}\033[0m")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        session.close()

def send_success_message(user_id):
    payment_logger.info(f"\033[93mНачало отправки успешного сообщения пользователю {user_id}\033[0m")
    
    global bot
    if not bot:
        payment_logger.error(f"\033[91mОшибка: переменная bot не инициализирована\033[0m")
        try:
            payment_logger.info(f"\033[93mПопытка инициализировать бота через initialize_bot()\033[0m")
            bot = initialize_bot()
            payment_logger.info(f"\033[92mБот успешно инициализирован для отправки приветственного сообщения\033[0m")
            
            # Проверяем токен бота после инициализации
            if hasattr(bot, 'token'):
                payment_logger.info(f"\033[93mТокен бота существует и имеет длину {len(bot.token)} символов\033[0m")
            else:
                payment_logger.error(f"\033[91mТокен бота не существует после инициализации\033[0m")
                
        except Exception as bot_init_error:
            payment_logger.error(f"\033[91mНе удалось инициализировать бота: {str(bot_init_error)}\033[0m")
            return False
    else:
        payment_logger.info(f"\033[93mБот уже инициализирован\033[0m")
    
    message = (
        "Спасибо за доверие. Ты сделал правильный выбор! "
        "Мы постараемся сделать все, чтобы помочь тебе прийти к своей цели.\n\n"
        "Давай введу тебя сразу в курс дела.\n\n"
        "По кнопкам внизу ты можешь:\n"
        "- получить доступ к приложению и личному кабинету, где тебя ждут твои программы,\n\n"
        "- добавиться в канал с анонсами мероприятий, прямых эфиров и просто "
        "полезной информацией о физическом и ментальном здоровье\n\n"
        "По кнопке menu ты можешь:\n"
        "- пообщаться с Health-ассистентом,\n"
        "- подобрать программу питания, сделать разбор анализов\n"
        "- управлять своей подпиской,\n"
        "- связаться с поддержкой, задать вопрос тренеру/нутрициологу/психологу\n\n"
        "- пригласить в наш сервис друга и получить бонусы, которыми можно оплатить "
        "подписку или вывести себе на счет."
    )
    
    payment_logger.info(f"\033[93mПолучение конфигурации бота\033[0m")
    config = get_bot_config()
    channel_url = config.get('channel_url', 'https://t.me/willway_channel')
    payment_logger.info(f"\033[93mПолучен URL канала: {channel_url}\033[0m")
    
    try:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="Доступ к приложению", web_app={"url": "https://willway.pro/app"})],
            [InlineKeyboardButton(text="Вступить в канал", url=channel_url)]
        ])
        payment_logger.info(f"\033[93mКлавиатура создана успешно\033[0m")
        
        payment_logger.info(f"\033[93mОтправка сообщения пользователю {user_id}\033[0m")
        try:
            result = bot.send_message(
                chat_id=user_id,
                text=message,
                reply_markup=keyboard
            )
            payment_logger.info(f"\033[92mСообщение успешно отправлено, результат: {result}\033[0m")
            return True
        except Exception as send_error:
            payment_logger.error(f"\033[91mОшибка при отправке сообщения: {str(send_error)}\033[0m")
            # Более подробная информация об ошибке
            import traceback
            payment_logger.error(f"\033[91mПодробная информация об ошибке: {traceback.format_exc()}\033[0m")
            return False
    except Exception as e:
        payment_logger.error(f"\033[91mОшибка при создании клавиатуры или отправке сообщения: {str(e)}\033[0m")
        # Более подробная информация об ошибке
        import traceback
        payment_logger.error(f"\033[91mПодробная информация об ошибке: {traceback.format_exc()}\033[0m")
        return False

def send_pending_message(user_id, manager_username):
    """Отправка сообщения о незавершенной оплате"""
    message = (
        "Мы видим, что ты начал(а) процесс оформления подписки, но не завершил оплату.\n\n"
        "Если у тебя возникли вопросы или тебе нужна помощь с оплатой, просто напиши мне здесь "
        "и я с радостью помогу тебе"
    )
    
    # Создаем клавиатуру с кнопками
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(text="Написать в поддержку", url=f"https://t.me/{manager_username}")],
        [InlineKeyboardButton(text="Посмотреть варианты подписки", url=f"https://willway.pro/payment?tgid={user_id}")]
    ])
    
    # Отправляем сообщение с клавиатурой
    bot.send_message(
        chat_id=user_id,
        text=message,
        reply_markup=keyboard
    )

@payment_bp.route('/api/v1/payment/check', methods=['POST'])
@require_api_key
def check_payment_status():
    """Проверка статуса оплаты"""
    data = request.json
    payment_logger.info(f"\033[93mПроверка статуса оплаты: {data}\033[0m")
    
    user_id = data.get('user_id')
    if not user_id:
        payment_logger.error("\033[91mНе указан user_id в запросе проверки статуса оплаты\033[0m")
        return jsonify({"status": "error", "message": "User ID is required"}), 400
    
    session = get_session()
    try:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            payment_logger.error(f"\033[91mПользователь с ID {user_id} не найден в базе данных\033[0m")
            return jsonify({"status": "error", "message": "User not found"}), 404
        
        payment_status = user.payment_status
        is_subscribed = user.is_subscribed
        welcome_sent = user.welcome_message_sent
        
        payment_logger.info(f"\033[93mПользователь {user_id}: payment_status={payment_status}, is_subscribed={is_subscribed}, welcome_message_sent={welcome_sent}\033[0m")
        
        # Получаем username менеджера из конфигурации
        config = get_bot_config()
        manager_username = config.get('manager_username', 'willway_manager')
        
        # Только если статус изменился с момента последней проверки, отправляем сообщение
        if payment_status == 'completed' and is_subscribed and not welcome_sent:
            payment_logger.info(f"\033[93mНеобходимо отправить приветственное сообщение для пользователя {user_id}\033[0m")
            # Отправляем сообщение об успешной оплате
            success = send_success_message(user_id)
            
            if success:
                # Обновляем флаг отправки приветственного сообщения
                payment_logger.info(f"\033[93mОбновляем welcome_message_sent с {welcome_sent} на True для пользователя {user_id}\033[0m")
                user.welcome_message_sent = True
                session.commit()
                payment_logger.info(f"\033[92mОтправлено приветственное сообщение пользователю {user_id}\033[0m")
            else:
                payment_logger.error(f"\033[91mНе удалось отправить приветственное сообщение пользователю {user_id}\033[0m")
        elif payment_status == 'pending' and not is_subscribed:
            payment_logger.info(f"\033[93mОтправка сообщения о незавершенной оплате для пользователя {user_id}\033[0m")
            send_pending_message(user_id, manager_username)
        else:
            payment_logger.info(f"\033[93mНе требуется отправка сообщений для пользователя {user_id}\033[0m")
        
        return jsonify({
            "status": "success",
            "data": {
                "payment_status": payment_status,
                "is_subscribed": is_subscribed
            }
        })
    except Exception as e:
        session.rollback()
        payment_logger.error(f"\033[91mОшибка при проверке статуса оплаты: {str(e)}\033[0m")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        session.close()

@payment_bp.route('/api/v1/payment/test_message/<int:user_id>', methods=['GET'])
def test_success_message(user_id):
    """
    Тестовый метод для проверки отправки приветственного сообщения
    """
    payment_logger.info(f"\033[93mТестовая отправка приветственного сообщения пользователю {user_id}\033[0m")
    
    try:
        success = send_success_message(user_id)
        if success:
            return jsonify({"status": "success", "message": "Test message sent successfully"})
        else:
            return jsonify({"status": "error", "message": "Failed to send test message"}), 500
    except Exception as e:
        payment_logger.error(f"\033[91mОшибка при тестовой отправке сообщения: {str(e)}\033[0m")
        return jsonify({"status": "error", "message": str(e)}), 500

def send_referral_bonus_notification(user_id, referral_username):
    """Отправка уведомления о начислении бонуса за приглашенного друга"""
    payment_logger.info(f"\033[93m[REFERRAL] Начало отправки уведомления о бонусе пользователю {user_id}\033[0m")
    
    global bot
    if not bot:
        payment_logger.error(f"\033[91m[REFERRAL] Ошибка при отправке уведомления - бот не инициализирован\033[0m")
        try:
            # Попытка инициализировать бота, если он не инициализирован
            bot = initialize_bot()
            payment_logger.info(f"\033[92m[REFERRAL] Бот успешно инициализирован для отправки уведомления\033[0m")
        except Exception as bot_init_error:
            payment_logger.error(f"\033[91m[REFERRAL] Не удалось инициализировать бота: {str(bot_init_error)}\033[0m")
            # Сохраняем уведомление в очередь для последующей отправки
            try:
                from database.models import PendingNotification
                session = get_session()
                pending = PendingNotification(
                    user_id=user_id,
                    message_type="referral_bonus",
                    data=json.dumps({"referral_username": referral_username}),
                    created_at=datetime.now()
                )
                session.add(pending)
                session.commit()
                payment_logger.info(f"\033[93m[REFERRAL] Уведомление сохранено в очередь для пользователя {user_id}\033[0m")
                session.close()
            except Exception as queue_error:
                payment_logger.error(f"\033[91m[REFERRAL] Ошибка при сохранении уведомления в очередь: {str(queue_error)}\033[0m")
            return False
    
    # Получаем данные о пользователе из БД для проверки
    session = get_session()
    try:
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            payment_logger.error(f"\033[91m[REFERRAL] Пользователь {user_id} не найден в базе данных\033[0m")
            return False
        
        # Проверяем, действительно ли у пользователя активна подписка
        if not user.is_subscribed or not user.subscription_expires:
            payment_logger.warning(f"\033[91m[REFERRAL] У пользователя {user_id} нет активной подписки, но отправляем уведомление\033[0m")
        else:
            payment_logger.info(f"\033[93m[REFERRAL] Подписка пользователя {user_id} активна до {user.subscription_expires}\033[0m")
        
        # Формируем сообщение с актуальной информацией о подписке
        subscription_end = user.subscription_expires.strftime("%d.%m.%Y") if user.subscription_expires else "неизвестно"
        message = (
            f"🎁 *Поздравляем!* Вы получили бонусный месяц подписки!\n\n"
            f"Ваш друг *{referral_username}* только что оплатил подписку по вашей реферальной ссылке.\n\n"
            f"Срок действия вашей подписки был продлен на 30 дней.\n"
            f"Текущая дата окончания подписки: *{subscription_end}*\n\n"
            f"Продолжайте приглашать друзей и получать бонусные месяцы!"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="Пригласить еще друзей", callback_data="invite_friend")],
            [InlineKeyboardButton(text="Управление подпиской", callback_data="subscription_management")]
        ])
        
        payment_logger.info(f"\033[93m[REFERRAL] Отправка уведомления пользователю {user_id}\033[0m")
        
        # Добавим повторные попытки при ошибках
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
                
                # Если успешно, отмечаем в базе, что бонус обработан
                try:
                    # Находим запись об использовании реферальной ссылки и отмечаем, что бонус выплачен
                    ref_use = session.query(ReferralUse).filter_by(
                        referrer_id=user.id,
                        subscription_purchased=True
                    ).order_by(ReferralUse.purchase_date.desc()).first()
                    
                    if ref_use and not getattr(ref_use, 'reward_processed', False):
                        # Проверяем, есть ли колонка reward_processed
                        try:
                            ref_use.reward_processed = True
                            session.commit()
                            payment_logger.info(f"\033[92m[REFERRAL] Отмечено, что бонус выплачен для записи ID={ref_use.id}\033[0m")
                        except Exception as column_error:
                            payment_logger.warning(f"\033[93m[REFERRAL] Колонка reward_processed не существует: {str(column_error)}\033[0m")
                except Exception as reward_error:
                    payment_logger.error(f"\033[91m[REFERRAL] Ошибка при отметке выплаты бонуса: {str(reward_error)}\033[0m")
                
                payment_logger.info(f"\033[92m[REFERRAL] Успешно отправлено уведомление о реферальном бонусе пользователю {user_id}\033[0m")
                return True
            except Exception as e:
                payment_logger.error(f"\033[91m[REFERRAL] Ошибка при отправке уведомления (попытка {attempt+1}/{max_retries}): {str(e)}\033[0m")
                time.sleep(1)  # Небольшая пауза перед повторной попыткой
        
        # Если все попытки не удались, сохраняем в очередь
        try:
            from database.models import PendingNotification
            pending = PendingNotification(
                user_id=user_id,
                message_type="referral_bonus",
                data=json.dumps({"referral_username": referral_username}),
                created_at=datetime.now()
            )
            session.add(pending)
            session.commit()
            payment_logger.info(f"\033[93m[REFERRAL] Уведомление сохранено в очередь после неудачных попыток для пользователя {user_id}\033[0m")
        except Exception as queue_error:
            payment_logger.error(f"\033[91m[REFERRAL] Ошибка при сохранении уведомления в очередь: {str(queue_error)}\033[0m")
        
        return False
    except Exception as e:
        payment_logger.error(f"\033[91m[REFERRAL] Ошибка при отправке уведомления о реферальном бонусе: {str(e)}\033[0m")
        return False
    finally:
        if 'session' in locals() and session:
            session.close() 