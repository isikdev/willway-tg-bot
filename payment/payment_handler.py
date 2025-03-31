import os
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from health_bot.database.airtable_integration import AirtablePaymentManager
from health_bot.payment.cloud_payments import CloudPaymentProcessor

load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Цены подписок
MONTHLY_SUBSCRIPTION_PRICE = 2222.0
YEARLY_SUBSCRIPTION_PRICE = 17777.0

class PaymentHandler:
    """Класс для обработки платежей в боте."""
    
    def __init__(self):
        """Инициализация обработчика платежей."""
        self.airtable_manager = AirtablePaymentManager()
        self.payment_processor = CloudPaymentProcessor()
        
    def generate_payment_link(self, user_data, subscription_type='monthly'):
        """
        Генерация ссылки на оплату.
        
        Args:
            user_data (dict): Данные пользователя (user_id, email, phone, username)
            subscription_type (str): Тип подписки (monthly/yearly)
            
        Returns:
            dict: Данные платежа с URL для оплаты
        """
        # Определение суммы в зависимости от типа подписки
        if subscription_type == 'monthly':
            amount = MONTHLY_SUBSCRIPTION_PRICE
            description = 'Месячная подписка WILLWAY'
        elif subscription_type == 'yearly':
            amount = YEARLY_SUBSCRIPTION_PRICE
            description = 'Годовая подписка WILLWAY'
        else:
            amount = MONTHLY_SUBSCRIPTION_PRICE
            description = 'Подписка WILLWAY'
        
        # Создание ссылки на оплату
        payment_data = self.payment_processor.create_payment_link(
            amount=amount,
            description=description,
            user_data=user_data,
            subscription_type=subscription_type
        )
        
        if payment_data:
            logger.info(f"Создана ссылка на оплату для пользователя {user_data.get('user_id')}")
            return payment_data
        else:
            logger.error(f"Ошибка при создании ссылки на оплату для пользователя {user_data.get('user_id')}")
            return None
    
    def check_payment_status(self, payment_id):
        """
        Проверка статуса платежа.
        
        Args:
            payment_id (str): Идентификатор платежа
            
        Returns:
            dict: Статус платежа
        """
        return self.payment_processor.check_payment_status(payment_id)
    
    def process_successful_payment(self, payment_data):
        """
        Обработка успешного платежа.
        
        Args:
            payment_data (dict): Данные платежа от обработчика webhook
            
        Returns:
            dict: Результат обработки платежа
        """
        # Извлечение данных
        user_data = payment_data.get('user_data', {})
        
        # Формирование данных о подписке
        subscription_data = {
            'amount': payment_data.get('amount'),
            'subscription_type': payment_data.get('subscription_type', 'monthly'),
            'expires': payment_data.get('expires_at')
        }
        
        # Создание записи в Airtable
        record = self.airtable_manager.create_payment_record(user_data, subscription_data)
        
        if record:
            return {
                'success': True,
                'user_id': user_data.get('user_id'),
                'subscription_type': subscription_data.get('subscription_type'),
                'expires_at': subscription_data.get('expires'),
                'record_id': record.get('id')
            }
        else:
            return {
                'success': False,
                'error': 'Ошибка при создании записи в Airtable'
            }
    
    def check_subscription_status(self, user_identifier, identifier_type='user_id'):
        """
        Проверка статуса подписки пользователя.
        
        Args:
            user_identifier (str): Идентификатор пользователя (user_id, email или phone)
            identifier_type (str): Тип идентификатора (user_id, email, phone)
            
        Returns:
            dict: Статус подписки
        """
        # Получение всех записей о платежах пользователя
        if identifier_type == 'user_id':
            records = self.airtable_manager.get_payment_records(user_identifier)
        else:
            # Получение всех записей и фильтрация по email или телефону вручную
            all_records = self.airtable_manager.get_payment_records()
            records = []
            
            for record in all_records:
                fields = record.get('fields', {})
                
                if identifier_type == 'email' and fields.get('email') == user_identifier:
                    records.append(record)
                elif identifier_type == 'phone' and fields.get('phone') == user_identifier:
                    records.append(record)
        
        if not records:
            return {
                'has_subscription': False,
                'message': 'Подписка не найдена'
            }
        
        # Поиск активной подписки
        active_subscription = None
        now = datetime.now()
        
        for record in records:
            fields = record.get('fields', {})
            
            # Проверка срока действия
            expires_str = fields.get('subscription_expires', '')
            if expires_str:
                try:
                    expires_date = datetime.fromisoformat(expires_str)
                    if expires_date > now and fields.get('status') == 'completed':
                        # Найдена активная подписка
                        if not active_subscription or datetime.fromisoformat(active_subscription.get('fields', {}).get('subscription_expires', '')) < expires_date:
                            active_subscription = record
                except (ValueError, TypeError) as e:
                    logger.error(f"Ошибка при обработке даты окончания подписки: {e}")
        
        if active_subscription:
            fields = active_subscription.get('fields', {})
            expires_date = datetime.fromisoformat(fields.get('subscription_expires', ''))
            days_left = (expires_date - now).days
            
            return {
                'has_subscription': True,
                'subscription_type': fields.get('subscription_type', 'unknown'),
                'expires_at': fields.get('subscription_expires', ''),
                'days_left': days_left,
                'record_id': active_subscription.get('id')
            }
        else:
            return {
                'has_subscription': False,
                'message': 'Активная подписка не найдена'
            }
    
    def update_payment_status_in_airtable(self, record_id, status):
        """
        Обновление статуса платежа в Airtable.
        
        Args:
            record_id (str): Идентификатор записи в Airtable
            status (str): Новый статус платежа
            
        Returns:
            dict: Обновленная запись
        """
        return self.airtable_manager.update_payment_status(record_id, status)
    
    def process_webhook(self, webhook_data):
        """
        Обработка вебхука от платежной системы.
        
        Args:
            webhook_data (dict): Данные вебхука
            
        Returns:
            dict: Результат обработки
        """
        payment_data = self.payment_processor.process_webhook(webhook_data)
        
        if payment_data:
            # Обработка успешного платежа
            return self.process_successful_payment(payment_data)
        else:
            logger.error("Ошибка при обработке вебхука")
            return {
                'success': False,
                'error': 'Ошибка при обработке вебхука'
            }

# Пример использования
if __name__ == "__main__":
    payment_handler = PaymentHandler()
    
    # Пример создания ссылки на оплату
    user_data = {
        'user_id': '12345678',
        'email': 'test@example.com',
        'phone': '+7 (999) 123-45-67',
        'username': 'test_user'
    }
    
    payment_link = payment_handler.generate_payment_link(
        user_data=user_data,
        subscription_type='monthly'
    )
    
    print(f"Ссылка на оплату: {payment_link}")
    
    # Пример проверки статуса подписки
    subscription_status = payment_handler.check_subscription_status('test@example.com', 'email')
    print(f"Статус подписки: {subscription_status}") 