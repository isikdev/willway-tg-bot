from flask import Blueprint, request, jsonify
import logging
from database.models import User, get_session
from datetime import datetime
import json

# Импортируем функцию для отправки уведомления из модуля обработчика отмены подписки
from bot.subscription_cancel_handler import process_subscription_webhook, check_subscription_cancellation

# Создаем Blueprint для маршрутов отмены подписки
subscription_cancel_bp = Blueprint('subscription_cancel', __name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@subscription_cancel_bp.route('/api/cancel-subscription-webhook', methods=['POST'])
def cancel_subscription_webhook():
    """
    Обработка вебхука от страницы отмены подписки
    """
    try:
        data = request.json
        logger.info(f"Получен вебхук отмены подписки: {data}")
        
        # Проверяем обязательные поля
        if not data or 'user_id' not in data:
            logger.error("Отсутствуют обязательные поля в запросе")
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        
        # Получаем бота для отправки уведомлений
        bot = None
        try:
            # Пробуем получить бота из run_bot
            from run_bot import bot as imported_bot
            bot = imported_bot
            logger.info(f"Успешно получен объект бота для отправки уведомления")
        except Exception as e:
            logger.warning(f"Не удалось получить объект бота: {e}")
        
        # Обрабатываем запрос отмены подписки
        result, status_code = process_subscription_webhook(data, bot)
        
        if status_code == 200:
            return jsonify({"success": True}), 200
        else:
            return jsonify({"success": False, "error": result.get("error", "Unknown error")}), status_code
    
    except Exception as e:
        logger.error(f"Ошибка при обработке вебхука отмены подписки: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@subscription_cancel_bp.route('/api/subscription-status', methods=['GET'])
def get_subscription_status():
    """
    Проверка статуса подписки пользователя
    """
    try:
        user_id = request.args.get('user_id')
        
        if not user_id:
            return jsonify({"success": False, "error": "Missing user_id parameter"}), 400
        
        session = get_session()
        user = session.query(User).filter(User.user_id == str(user_id)).first()
        
        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404
        
        subscription_data = {
            "is_subscribed": user.is_subscribed,
            "subscription_type": user.subscription_type,
            "subscription_expires": user.subscription_expires.isoformat() if user.subscription_expires else None
        }
        
        return jsonify({"success": True, "data": subscription_data}), 200
    
    except Exception as e:
        logger.error(f"Ошибка при получении статуса подписки: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()

@subscription_cancel_bp.route('/api/v1/subscription/cancel', methods=['POST'])
def cancel_subscription():
    """
    Эндпоинт для отмены подписки через JavaScript
    """
    try:
        data = request.json
        logger.info(f"Получен запрос на отмену подписки через API: {data}")
        
        if not data or 'user_id' not in data:
            logger.error("Отсутствует идентификатор пользователя в запросе")
            return jsonify({"success": False, "error": "Missing user_id"}), 400
        
        # Инициализируем бота для отправки уведомлений
        bot = None
        try:
            # Сначала пробуем получить бота из run_bot
            try:
                from run_bot import bot as imported_bot
                bot = imported_bot
                logger.info(f"Успешно получен объект бота из run_bot для отправки уведомления")
            except ImportError:
                logger.warning(f"Не удалось импортировать объект бота из run_bot, создаем новый экземпляр")
                
                # Если не удалось импортировать, создаем нового бота
                from telegram import Bot
                import os
                from bot.config import get_bot_config
                
                # Получаем токен из конфигурации
                config = get_bot_config()
                bot_token = config.get('bot_token') or os.getenv('TELEGRAM_BOT_TOKEN')
                
                if bot_token:
                    bot = Bot(token=bot_token)
                    logger.info(f"Создан новый экземпляр бота для отправки уведомления")
                else:
                    logger.error("Не удалось получить токен бота")
        except Exception as e:
            logger.error(f"Ошибка при инициализации бота: {e}")
        
        # Обрабатываем запрос отмены подписки через функцию-обработчик
        result, status_code = process_subscription_webhook(data, bot)
        
        if status_code == 200:
            # Успешная отмена подписки
            return jsonify({
                "success": True,
                "message": "Subscription successfully cancelled"
            }), 200
        else:
            # Ошибка при отмене подписки
            return jsonify({
                "success": False,
                "error": result.get("error", "Failed to cancel subscription")
            }), status_code
            
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса отмены подписки: {e}")
        return jsonify({
            "success": False, 
            "error": str(e)
        }), 500

@subscription_cancel_bp.route('/api/v1/subscription/cancel', methods=['GET'])
def cancel_subscription_get():
    """
    Обработка GET-запроса на отмену подписки (прямая ссылка)
    """
    try:
        user_id = request.args.get('user_id')
        status = request.args.get('status', 'cancelled')
        source = request.args.get('source', 'web_direct')
        
        if not user_id:
            return jsonify({"success": False, "error": "Missing user_id parameter"}), 400
        
        logger.info(f"Получен GET-запрос на отмену подписки: user_id={user_id}, status={status}, source={source}")
        
        # Формируем данные запроса в формате для process_subscription_webhook
        data = {
            'user_id': user_id,
            'status': status,
            'source': source,
            'timestamp': datetime.now().isoformat()
        }
        
        # Инициализируем бота для отправки уведомлений
        bot = None
        try:
            # Сначала пробуем получить бота из run_bot
            try:
                from run_bot import bot as imported_bot
                bot = imported_bot
                logger.info(f"Успешно получен объект бота из run_bot для отправки уведомления")
            except ImportError:
                logger.warning(f"Не удалось импортировать объект бота из run_bot, создаем новый экземпляр")
                
                # Если не удалось импортировать, создаем нового бота
                from telegram import Bot
                import os
                from bot.config import get_bot_config
                
                # Получаем токен из конфигурации
                config = get_bot_config()
                bot_token = config.get('bot_token') or os.getenv('TELEGRAM_BOT_TOKEN')
                
                if bot_token:
                    bot = Bot(token=bot_token)
                    logger.info(f"Создан новый экземпляр бота для отправки уведомления")
                else:
                    logger.error("Не удалось получить токен бота")
        except Exception as e:
            logger.error(f"Ошибка при инициализации бота: {e}")
        
        # Обрабатываем запрос отмены подписки через функцию-обработчик
        result, status_code = process_subscription_webhook(data, bot)
        
        if status_code == 200:
            # Если отмена успешна, отправляем HTML-страницу с сообщением об успехе
            success_html = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Подписка отменена</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        max-width: 600px;
                        margin: 40px auto;
                        padding: 20px;
                        text-align: center;
                    }
                    .success-container {
                        background-color: #f8f9fa;
                        border: 1px solid #ddd;
                        border-radius: 8px;
                        padding: 30px;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    }
                    h1 {
                        color: #28a745;
                        margin-bottom: 20px;
                    }
                    p {
                        font-size: 16px;
                        margin-bottom: 15px;
                    }
                    .back-button {
                        display: inline-block;
                        background-color: #007bff;
                        color: white;
                        text-decoration: none;
                        padding: 10px 20px;
                        border-radius: 5px;
                        margin-top: 20px;
                        transition: background-color 0.3s;
                    }
                    .back-button:hover {
                        background-color: #0069d9;
                    }
                </style>
            </head>
            <body>
                <div class="success-container">
                    <h1>Подписка успешно отменена</h1>
                    <p>Ваша подписка WILLWAY была успешно отменена.</p>
                    <p>Доступ к материалам сохранится до конца оплаченного периода.</p>
                    <p>Уведомление отправлено в Telegram.</p>
                    <a href="https://t.me/willwayapp_bot" class="back-button">Вернуться в бот</a>
                </div>
            </body>
            </html>
            """
            return success_html, 200, {'Content-Type': 'text/html; charset=utf-8'}
        else:
            # В случае ошибки отправляем JSON с ошибкой
            return jsonify({"success": False, "error": result.get("error", "Failed to process subscription cancellation")}), status_code
            
    except Exception as e:
        logger.error(f"Ошибка при обработке GET-запроса на отмену подписки: {e}")
        return jsonify({"success": False, "error": str(e)}), 500 