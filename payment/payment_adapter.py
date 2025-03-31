import os
import logging
import requests
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Cloud Payments API настройки
CLOUD_PAYMENTS_PUBLIC_ID = os.getenv('CLOUD_PAYMENTS_PUBLIC_ID')
CLOUD_PAYMENTS_API_KEY = os.getenv('CLOUD_PAYMENTS_API_KEY')

# Базовый URL API CloudPayments
BASE_URL = 'https://api.cloudpayments.ru'

class CloudPaymentAdapter:
    """Адаптер для интеграции CloudPayments в существующий бот"""
    
    def __init__(self):
        """Инициализация CloudPayments API."""
        if not all([CLOUD_PAYMENTS_PUBLIC_ID, CLOUD_PAYMENTS_API_KEY]):
            logger.warning("Не настроены переменные окружения для CloudPayments. Функциональность отключена.")
            self.enabled = False
        else:
            self.enabled = True
            self.auth = (CLOUD_PAYMENTS_PUBLIC_ID, CLOUD_PAYMENTS_API_KEY)
            logger.info("CloudPayments API успешно инициализирован")
    
    def generate_payment_link(self, amount, subscription_type='monthly', user_data=None):
        """
        Генерация платежной ссылки на основе данных пользователя.
        
        Args:
            amount (float): Сумма платежа
            subscription_type (str): Тип подписки (monthly/yearly)
            user_data (dict): Данные пользователя
            
        Returns:
            str: URL для оплаты или None в случае ошибки
        """
        if not self.enabled:
            logger.warning("CloudPayments API не инициализирован. Используется заглушка.")
            return f"https://link-to-payment-{subscription_type}.com"
            
        # Определяем валюту и описание
        currency = 'RUB'
        description = f"{'Месячная' if subscription_type == 'monthly' else 'Годовая'} подписка WILLWAY"
        
        # Определяем срок действия подписки
        if subscription_type == 'monthly':
            expires_at = datetime.now() + timedelta(days=30)
        else:  # yearly
            expires_at = datetime.now() + timedelta(days=365)
        
        # Подготовка данных для запроса
        payment_data = {
            'amount': amount,
            'currency': currency,
            'description': description,
            'requireEmail': True,
        }
        
        # Если есть данные пользователя, добавляем их
        if user_data:
            payment_data.update({
                'accountId': str(user_data.get('user_id', '')),
                'email': user_data.get('email', ''),
                'data': {
                    'subscription_type': subscription_type,
                    'expires_at': expires_at.isoformat(),
                    'phone': user_data.get('phone', '')
                }
            })
        
        try:
            logger.info(f"Отправка запроса на создание платежа: {payment_data}")
            response = requests.post(
                f"{BASE_URL}/orders/create",
                auth=self.auth,
                json=payment_data,
                headers={'Content-Type': 'application/json'}
            )
            
            response_data = response.json()
            logger.info(f"Ответ от CloudPayments: {response_data}")
            
            if response.status_code == 200 and response_data.get('Success'):
                logger.info("Платеж успешно создан")
                # Сохраняем order_id для последующих проверок
                payment_url = response_data.get('Model', {}).get('Url', '')
                payment_id = response_data.get('Model', {}).get('Id', '')
                
                return {
                    'payment_url': payment_url,
                    'payment_id': payment_id,
                    'amount': amount,
                    'subscription_type': subscription_type,
                    'expires_at': expires_at.isoformat()
                }
            else:
                logger.error(f"Ошибка при создании платежа: {response_data}")
                # Возвращаем заглушку в случае ошибки
                return f"https://link-to-payment-{subscription_type}.com"
                
        except Exception as e:
            logger.error(f"Ошибка при обращении к CloudPayments API: {e}")
            # Возвращаем заглушку в случае ошибки
            return f"https://link-to-payment-{subscription_type}.com"
    
    def check_payment_status(self, payment_id):
        """
        Проверка статуса платежа по ID.
        
        Args:
            payment_id (str): ID платежа
            
        Returns:
            bool: True если платеж успешно оплачен, иначе False
        """
        if not self.enabled or not payment_id:
            logger.warning("CloudPayments API не инициализирован или не указан ID платежа")
            return False
            
        try:
            response = requests.post(
                f"{BASE_URL}/orders/get",
                auth=self.auth,
                json={'Id': payment_id},
                headers={'Content-Type': 'application/json'}
            )
            
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get('Success'):
                status = response_data.get('Model', {}).get('Status', '')
                logger.info(f"Статус платежа {payment_id}: {status}")
                
                # Проверяем, что платеж завершен успешно
                if status == 'Completed':
                    return True
                    
            return False
                
        except Exception as e:
            logger.error(f"Ошибка при проверке статуса платежа: {e}")
            return False

# Создаем синглтон для использования в других модулях
payment_adapter = CloudPaymentAdapter() 