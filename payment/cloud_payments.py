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
WEBHOOK_BASE_URL = os.getenv('WEBHOOK_BASE_URL', 'http://localhost:5000')

# Базовый URL API CloudPayments
BASE_URL = 'https://api.cloudpayments.ru'

class CloudPaymentProcessor:
    """Класс для обработки платежей через Cloud Payments."""
    
    def __init__(self):
        """Инициализация CloudPayments API."""
        if not all([CLOUD_PAYMENTS_PUBLIC_ID, CLOUD_PAYMENTS_API_KEY]):
            logger.warning("Не настроены переменные окружения для CloudPayments. Функциональность отключена.")
            self.enabled = False
        else:
            self.enabled = True
            self.auth = (CLOUD_PAYMENTS_PUBLIC_ID, CLOUD_PAYMENTS_API_KEY)
            logger.info("CloudPayments API успешно инициализирован")
    
    def create_payment_link(self, amount, currency='RUB', description='Подписка WILLWAY', 
                            user_data=None, subscription_type='monthly'):
        """
        Создание ссылки на оплату.
        
        Args:
            amount (float): Сумма платежа
            currency (str): Валюта платежа (по умолчанию RUB)
            description (str): Описание платежа
            user_data (dict): Данные пользователя (email, телефон и т.д.)
            subscription_type (str): Тип подписки (monthly/yearly)
            
        Returns:
            dict: Ответ от API с данными для перенаправления на платеж
        """
        if not self.enabled:
            logger.info("CloudPayments API не инициализирован. Ссылка не будет создана.")
            return None
            
        # Подготовка данных о пользователе
        user_info = {}
        if user_data:
            user_info = {
                'email': user_data.get('email', ''),
                'phone': user_data.get('phone', ''),
                'account_id': str(user_data.get('user_id', '')),
                'description': description
            }
        
        # Установка срока действия подписки
        if subscription_type == 'monthly':
            expires_at = datetime.now() + timedelta(days=30)
        elif subscription_type == 'yearly':
            expires_at = datetime.now() + timedelta(days=365)
        else:
            expires_at = datetime.now() + timedelta(days=30)
        
        # Формирование данных для запроса
        payment_data = {
            'amount': amount,
            'currency': currency,
            'description': description,
            'accountId': user_info.get('account_id', ''),
            'email': user_info.get('email', ''),
            'requireEmail': True,
            'data': {
                'subscription_type': subscription_type,
                'expires_at': expires_at.isoformat(),
                'phone': user_info.get('phone', '')
            },
            'successUrl': f"{WEBHOOK_BASE_URL}/api/payment/success",
            'failUrl': f"{WEBHOOK_BASE_URL}/api/payment/fail"
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/orders/create",
                auth=self.auth,
                json=payment_data,
                headers={'Content-Type': 'application/json'}
            )
            
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get('Success'):
                logger.info(f"Создана ссылка на оплату: {response_data}")
                return {
                    'payment_url': response_data.get('Model', {}).get('Url', ''),
                    'payment_id': response_data.get('Model', {}).get('Id', ''),
                    'amount': amount,
                    'subscription_type': subscription_type,
                    'expires_at': expires_at.isoformat()
                }
            else:
                logger.error(f"Ошибка при создании ссылки на оплату: {response_data}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при обращении к CloudPayments API: {e}")
            return None
    
    def check_payment_status(self, payment_id):
        """
        Проверка статуса платежа.
        
        Args:
            payment_id (str): Идентификатор платежа
            
        Returns:
            dict: Статус платежа
        """
        if not self.enabled:
            logger.info("CloudPayments API не инициализирован. Невозможно проверить статус.")
            return None
            
        try:
            response = requests.post(
                f"{BASE_URL}/orders/get",
                auth=self.auth,
                json={'Id': payment_id},
                headers={'Content-Type': 'application/json'}
            )
            
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get('Success'):
                logger.info(f"Получен статус платежа: {response_data}")
                return {
                    'status': response_data.get('Model', {}).get('Status', ''),
                    'is_paid': response_data.get('Model', {}).get('Status', '') == 'Completed',
                    'payment_id': payment_id
                }
            else:
                logger.error(f"Ошибка при получении статуса платежа: {response_data}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при обращении к CloudPayments API: {e}")
            return None
    
    def process_webhook(self, webhook_data):
        """
        Обработка вебхука от CloudPayments.
        
        Args:
            webhook_data (dict): Данные вебхука от CloudPayments
            
        Returns:
            dict: Обработанные данные платежа
        """
        if not self.enabled:
            logger.info("CloudPayments API не инициализирован. Вебхук не будет обработан.")
            return None
            
        try:
            # Обработка различных типов вебхуков
            event_type = webhook_data.get('Type')
            
            if event_type == 'Pay':
                # Успешная оплата
                transaction_id = webhook_data.get('Id')
                amount = webhook_data.get('Amount')
                currency = webhook_data.get('Currency')
                
                # Данные пользователя и подписки
                data = webhook_data.get('Data', {})
                subscription_type = data.get('subscription_type', 'monthly')
                expires_at = data.get('expires_at')
                
                # Информация о пользователе
                account_id = webhook_data.get('AccountId')
                email = webhook_data.get('Email')
                phone = data.get('phone', '')
                
                return {
                    'transaction_id': transaction_id,
                    'amount': amount,
                    'currency': currency,
                    'status': 'completed',
                    'subscription_type': subscription_type,
                    'expires_at': expires_at,
                    'user_data': {
                        'user_id': account_id,
                        'email': email,
                        'phone': phone
                    }
                }
            else:
                logger.info(f"Получен вебхук неподдерживаемого типа: {event_type}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при обработке вебхука: {e}")
            return None

# Пример использования
if __name__ == "__main__":
    payment_processor = CloudPaymentProcessor()
    
    # Пример создания ссылки на оплату
    user_data = {
        'user_id': '12345678',
        'email': 'test@example.com',
        'phone': '+7 (999) 123-45-67'
    }
    
    # Месячная подписка
    payment_link = payment_processor.create_payment_link(
        amount=2222.0,
        description='Месячная подписка WILLWAY',
        user_data=user_data,
        subscription_type='monthly'
    )
    
    print(f"Ссылка на оплату: {payment_link}") 