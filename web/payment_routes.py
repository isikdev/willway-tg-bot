import os
import logging
from flask import Blueprint, request, jsonify, current_app, redirect, url_for, render_template
from health_bot.payment.payment_handler import PaymentHandler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Создание blueprint для платежных маршрутов
payment_routes = Blueprint('payment_routes', __name__)

# Инициализация обработчика платежей
payment_handler = PaymentHandler()

@payment_routes.route('/webhook/cloud-payments', methods=['POST'])
def cloud_payments_webhook():
    """
    Обработка вебхука от Cloud Payments.
    
    Returns:
        JSON ответ для Cloud Payments
    """
    try:
        webhook_data = request.json
        logger.info(f"Получен вебхук от Cloud Payments: {webhook_data}")
        
        # Обработка вебхука
        result = payment_handler.process_webhook(webhook_data)
        
        if result and result.get('success'):
            logger.info(f"Успешная обработка платежа: {result}")
            return jsonify({
                'code': 0,
                'message': 'Успешная обработка платежа'
            })
        else:
            logger.error(f"Ошибка при обработке платежа: {result}")
            return jsonify({
                'code': 1,
                'message': 'Ошибка при обработке платежа'
            }), 400
            
    except Exception as e:
        logger.error(f"Ошибка при обработке вебхука: {e}")
        return jsonify({
            'code': 2,
            'message': f'Внутренняя ошибка сервера: {str(e)}'
        }), 500

@payment_routes.route('/api/payment/success', methods=['GET'])
def payment_success():
    """
    Обработка успешной оплаты.
    
    Returns:
        HTML страница с сообщением об успешной оплате
    """
    payment_id = request.args.get('orderId', '')
    
    # Проверка статуса платежа
    if payment_id:
        status = payment_handler.check_payment_status(payment_id)
        if status and status.get('is_paid'):
            # Обработка успешного платежа
            return render_template('payment_success.html', 
                                  payment_id=payment_id,
                                  telegram_bot_url="https://t.me/willway_life_bot")
    
    # Если что-то пошло не так, показываем общее сообщение
    return render_template('payment_success.html', 
                          telegram_bot_url="https://t.me/willway_life_bot")

@payment_routes.route('/api/payment/fail', methods=['GET'])
def payment_fail():
    """
    Обработка неудачной оплаты.
    
    Returns:
        HTML страница с сообщением о неудачной оплате
    """
    payment_id = request.args.get('orderId', '')
    error = request.args.get('error', 'Неизвестная ошибка')
    
    # Записываем информацию об ошибке
    logger.error(f"Неудачная оплата: {payment_id}, ошибка: {error}")
    
    return render_template('payment_fail.html', 
                          error=error,
                          telegram_bot_url="https://t.me/willway_life_bot")

@payment_routes.route('/api/payment/check/<payment_id>', methods=['GET'])
def check_payment_status(payment_id):
    """
    Проверка статуса платежа.
    
    Args:
        payment_id (str): Идентификатор платежа
        
    Returns:
        JSON с информацией о статусе платежа
    """
    try:
        status = payment_handler.check_payment_status(payment_id)
        
        if status:
            return jsonify({
                'success': True,
                'status': status
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Платеж не найден'
            }), 404
            
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса платежа: {e}")
        return jsonify({
            'success': False,
            'message': f'Внутренняя ошибка сервера: {str(e)}'
        }), 500

@payment_routes.route('/api/subscription/check', methods=['POST'])
def check_subscription():
    """
    Проверка статуса подписки пользователя.
    
    Request JSON:
        {
            "identifier": "user_id_or_email_or_phone",
            "identifier_type": "user_id|email|phone"
        }
        
    Returns:
        JSON с информацией о статусе подписки
    """
    try:
        data = request.json
        identifier = data.get('identifier')
        identifier_type = data.get('identifier_type', 'user_id')
        
        if not identifier:
            return jsonify({
                'success': False,
                'message': 'Отсутствует идентификатор пользователя'
            }), 400
            
        status = payment_handler.check_subscription_status(identifier, identifier_type)
        
        return jsonify({
            'success': True,
            'subscription': status
        })
            
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса подписки: {e}")
        return jsonify({
            'success': False,
            'message': f'Внутренняя ошибка сервера: {str(e)}'
        }), 500

@payment_routes.route('/api/payment/create', methods=['POST'])
def create_payment():
    """
    Создание платежа.
    
    Request JSON:
        {
            "user_data": {
                "user_id": "telegram_user_id",
                "email": "user@example.com",
                "phone": "+7999123456",
                "username": "username"
            },
            "subscription_type": "monthly|yearly"
        }
        
    Returns:
        JSON с данными для оплаты
    """
    try:
        data = request.json
        user_data = data.get('user_data', {})
        subscription_type = data.get('subscription_type', 'monthly')
        
        if not user_data:
            return jsonify({
                'success': False,
                'message': 'Отсутствуют данные пользователя'
            }), 400
            
        payment_data = payment_handler.generate_payment_link(user_data, subscription_type)
        
        if payment_data:
            return jsonify({
                'success': True,
                'payment': payment_data
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Ошибка при создании платежа'
            }), 500
            
    except Exception as e:
        logger.error(f"Ошибка при создании платежа: {e}")
        return jsonify({
            'success': False,
            'message': f'Внутренняя ошибка сервера: {str(e)}'
        }), 500 