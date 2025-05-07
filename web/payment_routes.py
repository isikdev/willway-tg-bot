from dotenv import load_dotenv
from bot.handlers import get_bot_config
from database.models import get_session, User, Payment, ReferralUse, ReferralCode
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session, abort, current_app
import logging
from datetime import datetime, timedelta
import json
import os
import sys
from functools import wraps
import colorlog
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
import time
import re
import api_patch
from api_patch import register_conversion
# Отключаем импорт YooKassa, так как эта библиотека не используется
# from yookassa import Configuration, Payment as YooPayment
import uuid
import locale
# Отключаем импорт настроек YooKassa
# from config import FLASK_SECRET_KEY, YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY
from config import FLASK_SECRET_KEY

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))


load_dotenv()

# Функция для обновления записей конверсии блогера


def update_blogger_conversion(user_telegram_id, amount, session=None):
    """Обновляет запись о реферальной конверсии блогера после успешного платежа"""
    should_close_session = False

    try:
        # Если не передан session, создаем новый
        if not session:
            from database.models import get_session
            session = get_session()
            should_close_session = True

        # Ищем запись о переходе для этого пользователя
        from sqlalchemy import text
        result = session.execute(
            text("""
            SELECT br.id, br.blogger_id, b.name 
            FROM blogger_referrals br
            JOIN bloggers b ON br.blogger_id = b.id
            WHERE br.source LIKE :user_pattern AND br.converted = 0
            ORDER BY br.created_at DESC
            """),
            {"user_pattern": f"%{user_telegram_id}%"}
        )

        referral = result.fetchone()
        if referral:
            referral_id, blogger_id, blogger_name = referral

            # Рассчитываем комиссию (20% от суммы)
            commission = amount * 0.2

            # Обновляем запись о переходе
            from datetime import datetime
            current_time = datetime.now()

            session.execute(
                text("""
                UPDATE blogger_referrals 
                SET converted = 1, 
                    converted_at = :converted_at, 
                    commission_amount = :commission
                WHERE id = :referral_id
                """),
                {
                    "converted_at": current_time,
                    "commission": commission,
                    "referral_id": referral_id
                }
            )

            if should_close_session:
                session.commit()

            from logging import getLogger
            logger = getLogger('payment_system')
            logger.info(
                f"[BLOGGER_REFERRAL] Обновлена конверсия для блогера {blogger_name}, комиссия: {commission}")
            return True, f"Обновлена конверсия для блогера {blogger_name}, комиссия: {commission}"
        else:
            return False, "Реферальная запись не найдена"
    except Exception as e:
        from logging import getLogger
        logger = getLogger('payment_system')
        logger.error(
            f"[BLOGGER_REFERRAL] Ошибка при обновлении конверсии блогера: {str(e)}")
        return False, f"Ошибка при обновлении конверсии блогера: {str(e)}"
    finally:
        if should_close_session and 'session' in locals():
            session.close()


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
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

payment_logger = logging.getLogger('payment_system')
payment_logger.setLevel(logging.DEBUG)
payment_logger.addHandler(handler)
payment_logger.addHandler(file_handler)

payment_bp = Blueprint('payment', __name__)

# Получаем токен бота из конфигурации, а не из переменной окружения


def get_bot_token():
    try:
        import json
        import os
        bot_config_path = os.path.join(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))), 'bot_config.json')
        with open(bot_config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        token = config.get('bot_token')
        payment_logger.info(
            f"\033[93mТокен бота получен из bot_config.json: {'Да' if token else 'Нет'}\033[0m")
        if token:
            payment_logger.info(
                f"\033[93mДлина токена: {len(token)} символов\033[0m")
            return token
        else:
            # Запасной вариант - используем переменную окружения
            token = os.getenv("TELEGRAM_TOKEN")
            payment_logger.info(
                f"\033[93mТокен бота получен из переменной TELEGRAM_TOKEN: {'Да' if token else 'Нет'}\033[0m")
            return token
    except Exception as e:
        payment_logger.error(
            f"\033[91mОшибка при получении токена бота из конфигурации: {str(e)}\033[0m")
        # Запасной вариант - используем переменную окружения
        token = os.getenv("TELEGRAM_TOKEN")
        payment_logger.info(
            f"\033[93mТокен бота получен из переменной TELEGRAM_TOKEN: {'Да' if token else 'Нет'}\033[0m")
        return token


TELEGRAM_TOKEN = get_bot_token()
if not TELEGRAM_TOKEN:
    payment_logger.error(
        f"\033[91mТелеграм токен отсутствует! Проверьте bot_config.json или настройки .env файла\033[0m")

try:
    payment_logger.info(
        f"\033[93mПытаемся инициализировать бота с полученным токеном\033[0m")
    bot = Bot(token=TELEGRAM_TOKEN)
    payment_logger.info(f"\033[92mБот успешно инициализирован\033[0m")
except Exception as e:
    payment_logger.error(
        f"\033[91mОшибка при инициализации бота: {str(e)}\033[0m")
    import traceback
    payment_logger.error(
        f"\033[91mДетали ошибки: {traceback.format_exc()}\033[0m")
    bot = None

# Временное хранилище для соответствия между payment_user_id и telegram_id
# Формат: {payment_user_id: {"telegram_id": tg_id, "timestamp": time.time()}}
payment_user_mapping = {}

# Функция для очистки старых записей (старше 30 минут)


def cleanup_old_mappings():
    current_time = time.time()
    keys_to_delete = []
    for payment_id, data in payment_user_mapping.items():
        if current_time - data["timestamp"] > 1800:  # 30 минут
            keys_to_delete.append(payment_id)

    for key in keys_to_delete:
        del payment_user_mapping[key]

    if keys_to_delete:
        payment_logger.info(
            f"\033[93mУдалено {len(keys_to_delete)} устаревших записей из маппинга\033[0m")


def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function


@payment_bp.route('/api/v1/payment/track', methods=['POST'])
@require_api_key
def track_payment():
    """
    Отслеживает переход пользователя на страницу оплаты
    """
    data = request.json
    payment_logger.info(f"\033[93mДанные трекера платежа: {data}\033[0m")

    user_id = data.get('user_id')
    page = data.get('page', 'unknown')
    url = data.get('url', '')
    referrer = data.get('referrer', '')

    if not user_id:
        payment_logger.error(
            "\033[91mНе указан user_id в запросе трекера\033[0m")
        return jsonify({"status": "error", "message": "User ID is required"}), 400

    try:
        session = get_session()
        # Ищем пользователя по ID
        user = session.query(User).filter_by(user_id=user_id).first()

        # Если пользователь не найден, создаем нового
        if not user:
            payment_logger.info(
                f"\033[93mПользователь с ID {user_id} не найден, создаем нового\033[0m")
            user = User(
                user_id=user_id,
                registration_date=datetime.now(),
                payment_status='pending'
            )
            session.add(user)
            session.commit()
            user = session.query(User).filter_by(user_id=user_id).first()

        # Обновляем статус платежа на 'pending'
        user.payment_status = 'pending'
        session.commit()

        payment_logger.info(
            f"\033[94mСтатус платежа для пользователя {user.user_id} изменен на 'pending'\033[0m")

        response = jsonify({"status": "success", "message": "Payment tracking initiated"})
        # Добавляем CORS заголовки
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response
    except Exception as e:
        session.rollback()
        payment_logger.error(
            f"\033[91mОшибка при отслеживании платежа: {str(e)}\033[0m")
        response = jsonify({"status": "error", "message": str(e)}), 500
        # Добавляем CORS заголовки даже при ошибке
        response[0].headers.add('Access-Control-Allow-Origin', '*')
        response[0].headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response
    finally:
        session.close()


@payment_bp.route('/payment/success', methods=['GET'])
def payment_success():
    """
    Обработчик успешной оплаты
    """
    payment_id = request.args.get('payment_id')
    if not payment_id:
        abort(400, "Отсутствует идентификатор платежа")
    
    # Получаем данные пользователя из параметров
    session = None
    try:
        user_id = request.args.get('user_id')
        amount = float(request.args.get('amount', 0))
        payment_description = request.args.get('description', 'Подписка')

        if not user_id:
            abort(400, "Отсутствует идентификатор пользователя")
        
        user_id = int(user_id)
        
        # Получаем информацию о пользователе
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            session.close()
            abort(400, "Пользователь не найден")

        # Регистрируем платеж в БД
        # Создаем объект платежа
        new_payment = Payment(
            user_id=user.id,  # используем ID записи, а не telegram user_id
            payment_method='online',
            amount=amount,
            currency='RUB',  # По умолчанию рубли
            status='completed',
            subscription_type='monthly',
            paid_at=datetime.now()
        )
        
        # Если это платеж за подписку, обновляем статус подписки
        if 'subscription_' in payment_description:
            # Получаем тариф из описания (например, "subscription_premium_month")
            plan_parts = payment_description.split('_')
            if len(plan_parts) >= 2:
                plan_type = plan_parts[1]  # premium, standard и т.д.
                
                # Определяем длительность подписки
                duration = 30  # по умолчанию 30 дней
                if len(plan_parts) >= 3:
                    if plan_parts[2] == 'month':
                        duration = 30
                    elif plan_parts[2] == 'quarter':
                        duration = 90
                    elif plan_parts[2] == 'half_year':
                        duration = 180
                    elif plan_parts[2] == 'year':
                        duration = 365
                
                # Обновляем дату окончания подписки
                if user.subscription_expires and user.subscription_expires > datetime.now():
                    # Если подписка еще активна, продлеваем ее
                    user.subscription_expires = user.subscription_expires + timedelta(days=duration)
                else:
                    # Если подписка неактивна, устанавливаем новую дату окончания
                    user.subscription_expires = datetime.now() + timedelta(days=duration)

                # Устанавливаем подписку и её тип
                user.is_subscribed = True
                user.subscription_type = plan_type
                logging.info(f"Обновлен статус подписки для пользователя {user_id}: is_subscribed=True, type={plan_type}, до {user.subscription_expires}")
        
        # Если это разовый платеж, обрабатываем его соответственно
        if 'one_time_' in payment_description:
            logging.info(f"Обработка разового платежа для пользователя {user_id}: {payment_description}")
            # Здесь можно добавить логику для разовых платежей, например, открытие доступа к контенту
        
        # Сохраняем платеж и изменения пользователя
        session.add(new_payment)
        session.commit()

        # Регистрируем конверсию для блогера, если пользователь пришел по реферальной ссылке
        username = user.username if hasattr(user, 'username') else None
        
        try:
            conversion_result = register_conversion(user_id, amount, username)
            if conversion_result:
                logging.info(f"Успешно зарегистрирована конверсия для блогера от пользователя {user_id}")
            else:
                logging.info(f"Пользователь {user_id} не пришел по реферальной ссылке блогера или реферал не найден")
                
                # Проверяем и обрабатываем реферальный бонус для обычного пользователя
                try:
                    logging.info(f"Проверяем и обрабатываем реферальный бонус для пользователя {user.id}")
                    
                    # Сначала обновляем статус реферальной ссылки, чтобы отметить покупку
                    try:
                        # Находим запись об использовании реферальной ссылки
                        refUse = session.query(ReferralUse).filter(
                            ReferralUse.user_id == user.id,
                            ReferralUse.subscription_purchased == False
                        ).first()
                        
                        if refUse:
                            logging.info(f"Найдена запись об использовании реферальной ссылки ID={refUse.id}, обновляем статус покупки")
                            refUse.subscription_purchased = True
                            refUse.purchase_date = datetime.now()
                            session.commit()
                            logging.info(f"Статус покупки обновлен для реферальной записи ID={refUse.id}")
                    except Exception as update_error:
                        logging.error(f"Ошибка при обновлении статуса покупки: {str(update_error)}")
                    
                    # Затем обрабатываем бонус реферера
                    from web_admin.blogger_utils import process_referral_reward
                    logging.info(f"Функция process_referral_reward успешно импортирована")
                    
                    reward_result = process_referral_reward(user.id)
                    logging.info(f"Результат process_referral_reward: {reward_result}")
                    
                    if reward_result:
                        logging.info(f"Успешно начислен реферальный бонус за пользователя {user_id}")
                    else:
                        logging.info(f"Не найден реферер для пользователя {user_id} или бонус уже начислен")
                except Exception as reward_error:
                    logging.error(f"Ошибка при обработке реферального бонуса: {str(reward_error)}")
                    import traceback
                    logging.error(traceback.format_exc())
                
        except Exception as e:
            logging.error(f"Ошибка при регистрации конверсии: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
        
        if session:
            session.close()
        
        # Отправляем уведомление в Телеграм
        try:
            send_payment_notification(user_id, amount, payment_description)
        except Exception as e:
            logging.error(f"Ошибка при отправке уведомления о платеже: {str(e)}")
        
        return render_template('payment_success.html')
    
    except Exception as e:
        logging.error(f"Ошибка при обработке успешного платежа: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        if session:
            session.close()
        abort(500, "Произошла ошибка при обработке платежа")


@payment_bp.route('/api/v1/payment/success', methods=['POST'])
@require_api_key
def api_payment_success():
    """
    Обработчик успешной оплаты через API
    """
    data = request.json
    logging.info(f"Данные об успешной оплате: {data}")
    
    # Получаем данные из JSON
    try:
        user_id = data.get('user_id')
        amount = float(data.get('amount', 0))
        subscription_type = data.get('subscription_type', 'monthly')
        
        if not user_id:
            return jsonify({"status": "error", "message": "User ID is required"}), 400
        
        # Преобразуем user_id в int, если это строка
        if isinstance(user_id, str):
            try:
                user_id = int(user_id)
            except ValueError:
                logging.warning(f"Не удалось преобразовать user_id в int: {user_id}")

        # Получаем информацию о пользователе
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            # Если пользователь не найден, можно создать нового или отклонить запрос
            logging.warning(f"Пользователь {user_id} не найден в базе данных")
            session.close()
            return jsonify({"status": "error", "message": "User not found"}), 404
        
        # Регистрируем платеж в БД с правильными полями согласно модели Payment
        new_payment = Payment(
            user_id=user.id,  # используем ID записи, а не telegram user_id
            payment_method='online',
            amount=amount,
            currency='RUB',  # По умолчанию рубли
            status='completed',
            subscription_type=subscription_type,
            paid_at=datetime.now()
        )
        
        # Если это платеж за подписку, обновляем статус подписки
        if subscription_type:
            # Определяем длительность подписки
            duration = 30  # по умолчанию 30 дней (месяц)
            if subscription_type == 'yearly':
                duration = 365
            elif subscription_type == 'quarter':
                duration = 90
            elif subscription_type == 'half_year':
                duration = 180
            
            # Обновляем дату окончания подписки
            if user.subscription_expires and user.subscription_expires > datetime.now():
                # Если подписка еще активна, продлеваем ее
                user.subscription_expires = user.subscription_expires + timedelta(days=duration)
            else:
                # Если подписка неактивна, устанавливаем новую дату окончания
                user.subscription_expires = datetime.now() + timedelta(days=duration)
            
            # Устанавливаем флаг активной подписки и тип подписки
            user.is_subscribed = True
            user.subscription_type = subscription_type
            
            logging.info(f"Обновлен статус подписки для пользователя {user_id}: is_subscribed=True, тип={subscription_type}, до {user.subscription_expires}")

        # Сохраняем платеж и изменения пользователя
        session.add(new_payment)
        session.commit()
        
        # Логируем информацию об оплате
        log_payment(user_id, data)
        
        # Добавляем прямой импорт и вызов функции для обработки рефералов
        logging.info(f"[REFERRAL BONUS] Начинаем обработку реферального бонуса для user_id={user_id}")
        try:
            from web_admin.blogger_utils import process_referral_reward
            process_referral_reward(user_id)
            logging.info(f"[REFERRAL BONUS] Реферальный бонус успешно обработан для user_id={user_id}")
        except Exception as ref_err:
            logging.error(f"[REFERRAL BONUS] Ошибка при обработке реферального бонуса: {str(ref_err)}")
            import traceback
            logging.error(traceback.format_exc())
        
        # Регистрируем конверсию для блогера, если пользователь пришел по реферальной ссылке
        username = user.username if hasattr(user, 'username') else None
        
        try:
            conversion_result = register_conversion(user_id, amount, username)
            if conversion_result:
                logging.info(f"Успешно зарегистрирована конверсия для блогера от пользователя {user_id}")
            else:
                logging.info(f"Пользователь {user_id} не пришел по реферальной ссылке блогера или реферал не найден")
                
                # ВАЖНО: Добавляем явный вызов обработки реферального бонуса
                logging.info("ДИАГНОСТИКА: Запускаем прямой вызов process_referral_reward")
                
                # Находим запись использования реферальной ссылки для обычного пользователя
                try:
                    # Сначала обновляем статус реферальной ссылки, чтобы отметить покупку
                    referralUse = None
                    try:
                        # Находим запись об использовании реферальной ссылки
                        referralUse = session.query(ReferralUse).filter(
                            ReferralUse.user_id == user.id
                        ).first()
                        
                        if referralUse:
                            logging.info(f"ДИАГНОСТИКА: Найдена запись референса ID={referralUse.id}, referrer_id={referralUse.referrer_id}, подписка={getattr(referralUse, 'subscription_purchased', False)}")
                            referralUse.subscription_purchased = True
                            referralUse.purchase_date = datetime.now()
                            session.commit()
                            logging.info(f"ДИАГНОСТИКА: Статус покупки обновлен для реферальной записи ID={referralUse.id}")
                            
                            # Если нашли запись, пытаемся обработать бонус
                            try:
                                import sys
                                import os
                                # Добавляем корневую директорию в путь импорта
                                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                                if base_dir not in sys.path:
                                    sys.path.insert(0, base_dir)
                                    
                                logging.info(f"ДИАГНОСТИКА: Базовая директория: {base_dir}")
                                logging.info(f"ДИАГНОСТИКА: sys.path: {sys.path}")
                                
                                try:
                                    from web_admin.blogger_utils import process_referral_reward
                                    logging.info(f"ДИАГНОСТИКА: Функция process_referral_reward успешно импортирована")
                                    
                                    if referralUse and referralUse.referrer_id:
                                        reward_result = process_referral_reward(user.id, referralUse.referrer_id)
                                    else:
                                        reward_result = process_referral_reward(user.id)
                                    
                                    logging.info(f"ДИАГНОСТИКА: Результат process_referral_reward: {reward_result}")
                                    
                                    if reward_result:
                                        logging.info(f"ДИАГНОСТИКА: Успешно начислен реферальный бонус за пользователя {user_id}")
                                    else:
                                        logging.info(f"ДИАГНОСТИКА: Не найден реферер для пользователя {user_id} или бонус уже начислен")
                                except ImportError as import_err:
                                    logging.error(f"ДИАГНОСТИКА: Ошибка импорта process_referral_reward: {str(import_err)}")
                            except Exception as bonus_err:
                                logging.error(f"ДИАГНОСТИКА: Ошибка при обработке бонуса реферера: {str(bonus_err)}")
                                import traceback
                                logging.error(traceback.format_exc())
                    except Exception as update_error:
                        logging.error(f"ДИАГНОСТИКА: Ошибка при обновлении статуса покупки: {str(update_error)}")
                        import traceback
                        logging.error(traceback.format_exc())
                        
                except Exception as reward_error:
                    logging.error(f"ДИАГНОСТИКА: Общая ошибка при обработке реферального бонуса: {str(reward_error)}")
                    import traceback
                    logging.error(traceback.format_exc())
                
        except Exception as e:
            logging.error(f"Ошибка при регистрации конверсии: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
        
        session.close()

        # Отправляем уведомление в Телеграм
        try:
            send_success_message(user_id)
        except Exception as e:
            logging.error(f"Ошибка при отправке уведомления о платеже: {str(e)}")
        
        return jsonify({
            "status": "success",
            "message": "Payment successfully processed"
        })

    except Exception as e:
        logging.error(f"Ошибка при обработке успешной оплаты: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500


def send_success_message(user_id):
    payment_logger.info(
        f"\033[93mНачало отправки успешного сообщения пользователю {user_id}\033[0m")

    global bot
    if not bot:
        payment_logger.error(
            f"\033[91mОшибка: переменная bot не инициализирована\033[0m")
        try:
            # Получаем токен из bot_config.json
            token = get_bot_token()
            if not token:
                payment_logger.error(
                    f"\033[91mНе удалось получить токен бота\033[0m")
                return False

            payment_logger.info(
                f"\033[93mИнициализация бота с токеном из bot_config.json\033[0m")
            bot = Bot(token=token)
            payment_logger.info(
                f"\033[92mБот успешно инициализирован для отправки приветственного сообщения\033[0m")

        except Exception as bot_init_error:
            payment_logger.error(
                f"\033[91mНе удалось инициализировать бота: {str(bot_init_error)}\033[0m")
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
            [InlineKeyboardButton(text="Доступ к приложению", web_app={
                                  "url": "https://willway.pro/app"})],
            [InlineKeyboardButton(text="Вступить в канал", url=channel_url)]
        ])
        payment_logger.info(f"\033[93mКлавиатура создана успешно\033[0m")

        payment_logger.info(
            f"\033[93mОтправка сообщения пользователю {user_id}\033[0m")
        try:
            result = bot.send_message(
                chat_id=user_id,
                text=message,
                reply_markup=keyboard
            )
            payment_logger.info(
                f"\033[92mСообщение успешно отправлено, результат: {result}\033[0m")
            return True
        except Exception as send_error:
            payment_logger.error(
                f"\033[91mОшибка при отправке сообщения: {str(send_error)}\033[0m")
            # Более подробная информация об ошибке
            import traceback
            payment_logger.error(
                f"\033[91mПодробная информация об ошибке: {traceback.format_exc()}\033[0m")
            return False
    except Exception as e:
        payment_logger.error(
            f"\033[91mОшибка при создании клавиатуры или отправке сообщения: {str(e)}\033[0m")
        # Более подробная информация об ошибке
        import traceback
        payment_logger.error(
            f"\033[91mПодробная информация об ошибке: {traceback.format_exc()}\033[0m")
        return False


def send_pending_message(user_id):
    payment_logger.info(
        f"\033[93mНачало отправки сообщения о незавершенной оплате пользователю {user_id}\033[0m")

    global bot
    if not bot:
        payment_logger.error(
            f"\033[91mОшибка: переменная bot не инициализирована\033[0m")
        try:
            # Получаем токен из bot_config.json
            token = get_bot_token()
            if not token:
                payment_logger.error(
                    f"\033[91mНе удалось получить токен бота\033[0m")
                return False

            payment_logger.info(
                f"\033[93mИнициализация бота с токеном из bot_config.json\033[0m")
            bot = Bot(token=token)
            payment_logger.info(
                f"\033[92mБот успешно инициализирован для отправки сообщения о незавершенной оплате\033[0m")

        except Exception as bot_init_error:
            payment_logger.error(
                f"\033[91mНе удалось инициализировать бота: {str(bot_init_error)}\033[0m")
            return False
    else:
        payment_logger.info(f"\033[93mБот уже инициализирован\033[0m")

    # Получаем имя пользователя менеджера из конфигурации
    try:
        with open('bot/bot_config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            manager_username = config.get(
                'manager_username', 'willway_support')
    except Exception as e:
        payment_logger.error(
            f"\033[91mОшибка при получении имени менеджера: {str(e)}\033[0m")
        manager_username = 'willway_support'  # Значение по умолчанию

    # Текст сообщения
    message = (
        "Мы видим, что ты начал(а) процесс оформления подписки, но не завершил оплату.\n\n"
        "Если у тебя возникли вопросы или тебе нужна помощь с оплатой, просто напиши мне здесь "
        "и я с радостью помогу тебе"
    )

    # Создаем клавиатуру с кнопками
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(text="Написать в поддержку",
                              url=f"https://t.me/{manager_username}")],
        [InlineKeyboardButton(text="Посмотреть варианты подписки",
                              url=f"https://willway.pro/payment?tgid={user_id}")]
    ])

    # Отправляем сообщение с клавиатурой
    try:
        bot.send_message(
            chat_id=user_id,
            text=message,
            reply_markup=keyboard
        )
        payment_logger.info(
            f"\033[92mОтправлено сообщение о незавершенной оплате пользователю {user_id}\033[0m")
        return True
    except Exception as e:
        payment_logger.error(
            f"\033[91mОшибка при отправке сообщения о незавершенной оплате: {str(e)}\033[0m")
        return False


@payment_bp.route('/api/v1/payment/check', methods=['POST'])
@require_api_key
def check_payment_status():
    """
    Проверяет статус платежа пользователя
    """
    data = request.json
    payment_logger.info(f"\033[93mЗапрос на проверку статуса платежа: {data}\033[0m")

    user_id = data.get('user_id')
    
    if not user_id:
        payment_logger.error(
            "\033[91mНе указан user_id в запросе проверки статуса\033[0m")
        error_response = jsonify({"status": "error", "message": "User ID is required"}), 400
        # Добавляем CORS заголовки к ответу с ошибкой
        error_response[0].headers.add('Access-Control-Allow-Origin', '*')
        error_response[0].headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        error_response[0].headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return error_response

    session = get_session()
    try:
        # Ищем пользователя
        user = session.query(User).filter_by(user_id=user_id).first()
        
        if not user:
            # Если пользователь с таким ID не найден, проверяем маппинг
            if str(user_id) in payment_user_mapping:
                tg_id = payment_user_mapping[str(user_id)]["telegram_id"]
                user = session.query(User).filter_by(user_id=tg_id).first()
                payment_logger.info(
                    f"\033[94mНайден пользователь через маппинг: {user_id} -> {tg_id}\033[0m")
        
        if not user:
            payment_logger.warning(
                f"\033[93mПользователь с ID {user_id} не найден в базе данных\033[0m")
            response = jsonify({
                "status": "error",
                "message": "User not found",
                "payment_status": "unknown"
            })
            # Добавляем CORS заголовки к ответу
            response.headers.add('Access-Control-Allow-Origin', '*')
            response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
            response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
            return response
        
        # Получаем статус платежа
        payment_status = user.payment_status or "unknown"
        is_subscribed = user.is_subscribed or False
        
        # Если есть подписка, проверяем, не истекла ли она
        subscription_active = False
        subscription_expires = None
        remaining_days = 0
        
        if is_subscribed and user.subscription_expires:
            subscription_expires = user.subscription_expires
            now = datetime.now()
            
            if subscription_expires > now:
                subscription_active = True
                remaining_days = (subscription_expires - now).days
        
        payment_logger.info(
            f"\033[94mСтатус платежа для пользователя {user_id}: {payment_status}, подписка активна: {subscription_active}\033[0m")
        
        # Если статус pending и пользователь не подписан, отправляем напоминание
        if payment_status == 'pending' and not subscription_active:
            # Получаем username менеджера
            config = get_bot_config()
            manager_username = config.get("manager_username", "willway_manager")
            
            # Отправляем напоминание о незавершенной оплате через бота
            try:
                if bot and user.user_id:
                    # Чтобы не отправлять слишком много напоминаний, проверяем когда было отправлено последнее
                    last_reminder = user.last_payment_reminder or datetime.now() - timedelta(hours=24)
                    
                    # Если прошло больше часа с последнего напоминания
                    if datetime.now() - last_reminder > timedelta(hours=1):
                        payment_logger.info(
                            f"\033[93mОтправка напоминания о незавершенной оплате пользователю {user.user_id}\033[0m")
                        send_pending_message(user.user_id)
                        
                        # Обновляем время последнего напоминания
                        user.last_payment_reminder = datetime.now()
                        session.commit()
                    else:
                        payment_logger.info(
                            f"\033[93mНапоминание о незавершенной оплате пользователю {user.user_id} уже было отправлено недавно\033[0m")
            except Exception as bot_error:
                payment_logger.error(
                    f"\033[91mОшибка при отправке напоминания через бота: {str(bot_error)}\033[0m")

        # Формируем ответ
        success_response = jsonify({
            "status": "success",
            "user_id": user.user_id,
            "payment_status": payment_status,
            "is_subscribed": subscription_active,
            "subscription_expires": subscription_expires.isoformat() if subscription_expires else None,
            "remaining_days": remaining_days
        })
        # Добавляем CORS заголовки к успешному ответу
        success_response.headers.add('Access-Control-Allow-Origin', '*')
        success_response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        success_response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return success_response
        
    except Exception as e:
        payment_logger.error(
            f"\033[91mОшибка при проверке статуса платежа: {str(e)}\033[0m")
        error_response = jsonify({"status": "error", "message": str(e)}), 500
        # Добавляем CORS заголовки к ответу с ошибкой
        error_response[0].headers.add('Access-Control-Allow-Origin', '*')
        error_response[0].headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        error_response[0].headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return error_response
    finally:
        session.close()


@payment_bp.route('/api/v1/payment/test_message/<int:user_id>', methods=['GET'])
def test_success_message(user_id):
    """
    Тестовый метод для проверки отправки приветственного сообщения
    """
    payment_logger.info(
        f"\033[93mТестовая отправка приветственного сообщения пользователю {user_id}\033[0m")

    try:
        success = send_success_message(user_id)
        if success:
            return jsonify({"status": "success", "message": "Test message sent successfully"})
        else:
            return jsonify({"status": "error", "message": "Failed to send test message"}), 500
    except Exception as e:
        payment_logger.error(
            f"\033[91mОшибка при тестовой отправке сообщения: {str(e)}\033[0m")
        return jsonify({"status": "error", "message": str(e)}), 500


def send_referral_bonus_notification(user_id, referral_username):
    """Отправка уведомления о начислении бонуса за приглашенного друга"""
    payment_logger.info(
        f"\033[93m[REFERRAL] Начало отправки уведомления о бонусе пользователю {user_id}, приглашенный: {referral_username}\033[0m")

    global bot
    if not bot:
        payment_logger.error(
            f"\033[91m[REFERRAL] Ошибка при отправке уведомления - бот не инициализирован\033[0m")
        try:
            # Попытка инициализировать бота, если он не инициализирован
            token = get_bot_token()
            if not token:
                payment_logger.error(
                    f"\033[91m[REFERRAL] Не удалось получить токен бота\033[0m")
                return False

            bot = Bot(token=token)
            payment_logger.info(
                f"\033[92m[REFERRAL] Бот успешно инициализирован для отправки уведомления\033[0m")
        except Exception as bot_init_error:
            payment_logger.error(
                f"\033[91m[REFERRAL] Не удалось инициализировать бота: {str(bot_init_error)}\033[0m")
            import traceback
            payment_logger.error(f"\033[91m[REFERRAL] Трассировка ошибки: {traceback.format_exc()}\033[0m")
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
                payment_logger.info(
                    f"\033[93m[REFERRAL] Уведомление сохранено в очередь для пользователя {user_id}\033[0m")
                session.close()
            except Exception as queue_error:
                payment_logger.error(
                    f"\033[91m[REFERRAL] Ошибка при сохранении уведомления в очередь: {str(queue_error)}\033[0m")
                import traceback
                payment_logger.error(f"\033[91m[REFERRAL] Трассировка ошибки: {traceback.format_exc()}\033[0m")
            return False

    # Ищем пользователя в БД
    session = get_session()
    try:
        payment_logger.info(f"\033[93m[REFERRAL] Поиск пользователя с user_id={user_id}\033[0m")
        user = session.query(User).filter_by(user_id=user_id).first()
        if not user:
            payment_logger.error(
                f"\033[91m[REFERRAL] Пользователь {user_id} не найден в базе данных\033[0m")
            
            # Пробуем найти по id записи
            payment_logger.info(f"\033[93m[REFERRAL] Пробуем найти пользователя по id записи={user_id}\033[0m")
            user = session.query(User).filter_by(id=user_id).first()
            if user:
                payment_logger.info(f"\033[93m[REFERRAL] Пользователь найден по id записи: user_id={user.user_id}\033[0m")
                user_id = user.user_id  # Используем правильный user_id из Telegram
            else:
                payment_logger.error(f"\033[91m[REFERRAL] Пользователь не найден ни по user_id, ни по id записи\033[0m")
                return False

        # Проверяем, действительно ли у пользователя активна подписка
        payment_logger.info(f"\033[93m[REFERRAL] Проверка подписки пользователя {user_id}: is_subscribed={user.is_subscribed}, expires={user.subscription_expires}\033[0m")
        if not user.is_subscribed or not user.subscription_expires:
            payment_logger.warning(
                f"\033[91m[REFERRAL] У пользователя {user_id} нет активной подписки, но отправляем уведомление\033[0m")
        else:
            payment_logger.info(
                f"\033[93m[REFERRAL] Подписка пользователя {user_id} активна до {user.subscription_expires}\033[0m")

        # Формируем сообщение с актуальной информацией о подписке
        subscription_end = user.subscription_expires.strftime(
            "%d.%m.%Y") if user.subscription_expires else "неизвестно"
        message = (
            f"🎁 *Поздравляем!* Вы получили бонусный месяц подписки!\n\n"
            f"Ваш друг *{referral_username}* только что оплатил подписку по вашей реферальной ссылке.\n\n"
            f"Срок действия вашей подписки был продлен на 30 дней.\n"
            f"Текущая дата окончания подписки: *{subscription_end}*\n\n"
            f"Продолжайте приглашать друзей и получать бонусные месяцы!"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                text="Пригласить еще друзей", callback_data="invite_friend")],
            [InlineKeyboardButton(
                text="Управление подпиской", callback_data="subscription_management")]
        ])

        payment_logger.info(
            f"\033[93m[REFERRAL] Отправка уведомления пользователю {user_id}\033[0m")

        # Добавим повторные попытки при ошибках
        max_retries = 3
        for attempt in range(max_retries):
            try:
                payment_logger.info(f"\033[93m[REFERRAL] Попытка #{attempt+1} отправки уведомления пользователю {user_id}\033[0m")
                response = bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )

                payment_logger.info(f"\033[93m[REFERRAL] Ответ отправки: {response}\033[0m")

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
                            payment_logger.info(
                                f"\033[92m[REFERRAL] Отмечено, что бонус выплачен для записи ID={ref_use.id}\033[0m")
                        except Exception as column_error:
                            payment_logger.warning(
                                f"\033[93m[REFERRAL] Колонка reward_processed не существует: {str(column_error)}\033[0m")
                            # Пытаемся добавить колонку
                            try:
                                from sqlalchemy import text
                                session.execute(text("ALTER TABLE referral_use ADD COLUMN IF NOT EXISTS reward_processed BOOLEAN DEFAULT FALSE"))
                                session.commit()
                                # Устанавливаем значение
                                session.execute(
                                    text("UPDATE referral_use SET reward_processed = :value WHERE id = :id"),
                                    {"value": True, "id": ref_use.id}
                                )
                                session.commit()
                                payment_logger.info(
                                    f"\033[92m[REFERRAL] Добавлена колонка reward_processed и установлено значение для записи ID={ref_use.id}\033[0m")
                            except Exception as add_column_error:
                                payment_logger.error(
                                    f"\033[91m[REFERRAL] Ошибка при добавлении колонки: {str(add_column_error)}\033[0m")
                                import traceback
                                payment_logger.error(f"\033[91m[REFERRAL] Трассировка ошибки: {traceback.format_exc()}\033[0m")
                except Exception as reward_error:
                    payment_logger.error(
                        f"\033[91m[REFERRAL] Ошибка при отметке выплаты бонуса: {str(reward_error)}\033[0m")
                    import traceback
                    payment_logger.error(f"\033[91m[REFERRAL] Трассировка ошибки: {traceback.format_exc()}\033[0m")

                payment_logger.info(
                    f"\033[92m[REFERRAL] Успешно отправлено уведомление о реферальном бонусе пользователю {user_id}\033[0m")
                return True
            except Exception as e:
                payment_logger.error(
                    f"\033[91m[REFERRAL] Ошибка при отправке уведомления (попытка {attempt+1}/{max_retries}): {str(e)}\033[0m")
                import traceback
                payment_logger.error(f"\033[91m[REFERRAL] Трассировка ошибки: {traceback.format_exc()}\033[0m")
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
            payment_logger.info(
                f"\033[93m[REFERRAL] Уведомление сохранено в очередь после неудачных попыток для пользователя {user_id}\033[0m")
        except Exception as queue_error:
            payment_logger.error(
                f"\033[91m[REFERRAL] Ошибка при сохранении уведомления в очередь: {str(queue_error)}\033[0m")
            import traceback
            payment_logger.error(f"\033[91m[REFERRAL] Трассировка ошибки: {traceback.format_exc()}\033[0m")

        return False
    except Exception as e:
        payment_logger.error(
            f"\033[91m[REFERRAL] Ошибка при отправке уведомления о реферальном бонусе: {str(e)}\033[0m")
        import traceback
        payment_logger.error(f"\033[91m[REFERRAL] Трассировка ошибки: {traceback.format_exc()}\033[0m")
        return False
    finally:
        if 'session' in locals() and session:
            session.close()

# Функция для отладки состояния маппинга


def log_mapping_state():
    if not payment_user_mapping:
        payment_logger.info(f"\033[93m[DEBUG] Маппинг пуст\033[0m")
        return

    payment_logger.info(
        f"\033[93m[DEBUG] Текущее состояние маппинга (всего {len(payment_user_mapping)} записей):\033[0m")
    for payment_id, data in payment_user_mapping.items():
        payment_logger.info(
            f"\033[93m[DEBUG] - Плательщик {payment_id} -> Telegram {data['telegram_id']} (создан {time.strftime('%H:%M:%S', time.localtime(data['timestamp']))})\033[0m")

# Логируем состояние мапинга в начале обработки запросов


@payment_bp.before_request
def before_request():
    # Логируем только для определенных маршрутов
    if request.path.startswith('/api/v1/payment/'):
        payment_logger.info(f"\033[93m[REQUEST] {request.method} {request.path}\033[0m")

# Логируем состояние мапинга после обработки запросов


@payment_bp.after_request
def after_request(response):
    # Логируем только для определенных маршрутов
    if request.path.startswith('/api/v1/payment/'):
        payment_logger.info(f"\033[93m[RESPONSE] {request.method} {request.path} - Status: {response.status_code}\033[0m")
    return response

# Обработчик CORS preflight запросов
@payment_bp.route('/api/v1/payment/track', methods=['OPTIONS'])
@payment_bp.route('/api/v1/payment/success', methods=['OPTIONS'])
@payment_bp.route('/api/v1/payment/check', methods=['OPTIONS'])
def handle_preflight():
    """Обработчик CORS preflight запросов"""
    response = jsonify({'status': 'ok'})
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Отключаем настройки YooKassa, так как библиотека не используется
# Configuration.account_id = YOOKASSA_SHOP_ID
# Configuration.secret_key = YOOKASSA_SECRET_KEY

# Отключаем создание клиента YooKassa
# client = YooPayment.client()

def send_payment_notification(user_id, amount, payment_description):
    """
    Отправляет уведомление в Telegram о успешной оплате
    """
    payment_logger.info(f"Отправка уведомления об успешной оплате пользователю {user_id}")
    
    global bot
    if not bot:
        payment_logger.error("Ошибка: переменная bot не инициализирована")
        try:
            token = get_bot_token()
            if not token:
                payment_logger.error("Не удалось получить токен бота")
                return False
            
            payment_logger.info("Инициализация бота с полученным токеном")
            bot = Bot(token=token)
            payment_logger.info("Бот успешно инициализирован для отправки уведомления об оплате")
        except Exception as bot_init_error:
            payment_logger.error(f"Не удалось инициализировать бота: {str(bot_init_error)}")
            return False
    
    # Получаем тип подписки из описания платежа
    subscription_type = "Стандартная"
    if "premium" in payment_description.lower():
        subscription_type = "Премиум"
    elif "vip" in payment_description.lower():
        subscription_type = "VIP"
    
    # Получаем продолжительность подписки
    duration = "30 дней"
    if "quarter" in payment_description.lower():
        duration = "90 дней"
    elif "half_year" in payment_description.lower():
        duration = "180 дней"
    elif "year" in payment_description.lower():
        duration = "365 дней"
    
    # Форматируем сумму платежа
    formatted_amount = f"{amount:.2f}".replace('.', ',')
    
    # Текст сообщения
    message = (
        f"✅ *Оплата успешно произведена!*\n\n"
        f"Сумма: *{formatted_amount} руб.*\n"
        f"Тип подписки: *{subscription_type}*\n"
        f"Продолжительность: *{duration}*\n\n"
        f"Благодарим за доверие! Ваша подписка активирована.\n"
        f"Теперь Вам доступны все возможности сервиса WillWay."
    )
    
    # Создаем клавиатуру с кнопками
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(text="Перейти в приложение", web_app={"url": "https://willway.pro/app"})],
        [InlineKeyboardButton(text="Настройки подписки", callback_data="subscription_settings")]
    ])
    
    # Отправляем сообщение с клавиатурой
    try:
        result = bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        payment_logger.info(f"Сообщение об успешной оплате отправлено пользователю {user_id}")
        
        # Отправляем успешное сообщение
        send_success_message(user_id)
        
        return True
    except Exception as e:
        payment_logger.error(f"Ошибка при отправке уведомления об оплате: {str(e)}")
        import traceback
        payment_logger.error(f"Подробности: {traceback.format_exc()}")
        return False

# Добавляем функцию для логирования платежей
def log_payment(user_id, payment_data):
    """
    Логирует информацию о платеже в файл логов
    """
    payment_logger.info(f"\033[92m[PAYMENT_LOG] Успешная оплата от пользователя {user_id}\033[0m")
    payment_logger.info(f"\033[92m[PAYMENT_LOG] Данные платежа: {payment_data}\033[0m")
    
    try:
        # Если есть желание дополнительно сохранять информацию о платежах в базе данных
        # здесь можно добавить соответствующий код
        pass
    except Exception as e:
        payment_logger.error(f"\033[91m[PAYMENT_LOG] Ошибка при логировании платежа: {str(e)}\033[0m")
