import os
from pyairtable import Api
from dotenv import load_dotenv
import logging
from datetime import datetime

load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Airtable API настройки
AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
AIRTABLE_TABLE_NAME = os.getenv('AIRTABLE_TABLE_NAME')

class AirtablePaymentManager:
    """Класс для работы с платежами через Airtable."""
    
    def __init__(self):
        """Инициализация API Airtable."""
        self.api = None
        self.table = None
        
        if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME]):
            logger.warning("Не настроены переменные окружения для Airtable. Функциональность отключена.")
            return
            
        try:
            self.api = Api(AIRTABLE_API_KEY)
            self.table = self.api.table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME)
            logger.info("Airtable API успешно инициализирован")
        except Exception as e:
            logger.error(f"Ошибка при инициализации Airtable API: {e}")
    
    def create_payment_record(self, user_data, payment_data):
        """Создание записи о платеже в Airtable."""
        if not self.api or not self.table:
            logger.info("Airtable API не инициализирован. Запись не будет создана.")
            return None
            
        try:
            record = {
                'user_id': str(user_data.get('user_id')),
                'username': user_data.get('username', ''),
                'payment_amount': payment_data.get('amount', ''),
                'subscription_type': payment_data.get('subscription_type', ''),
                'payment_date': datetime.now().isoformat(),
                'subscription_expires': payment_data.get('expires', ''),
                'status': 'completed'
            }
            
            created_record = self.table.create(record)
            logger.info(f"Создана запись в Airtable: {created_record}")
            return created_record
        except Exception as e:
            logger.error(f"Ошибка при создании записи в Airtable: {e}")
            return None
    
    def get_payment_records(self, user_id=None):
        """Получение записей о платежах из Airtable."""
        if not self.api or not self.table:
            logger.info("Airtable API не инициализирован. Невозможно получить записи.")
            return []
            
        try:
            if user_id:
                formula = f"{{user_id}} = '{user_id}'"
                records = self.table.all(formula=formula)
            else:
                records = self.table.all()
            
            return records
        except Exception as e:
            logger.error(f"Ошибка при получении записей из Airtable: {e}")
            return []
    
    def update_payment_status(self, record_id, status):
        """Обновление статуса платежа в Airtable."""
        if not self.api or not self.table:
            logger.info("Airtable API не инициализирован. Невозможно обновить статус.")
            return None
            
        try:
            updated_record = self.table.update(record_id, {'status': status})
            logger.info(f"Обновлен статус записи в Airtable: {updated_record}")
            return updated_record
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса в Airtable: {e}")
            return None

# Пример использования
if __name__ == "__main__":
    payment_manager = AirtablePaymentManager()
    
    # Пример создания записи о платеже
    user_data = {
        'user_id': '12345678',
        'username': 'test_user'
    }
    
    payment_data = {
        'amount': '1,890р',
        'subscription_type': 'monthly',
        'expires': datetime(2023, 12, 31).isoformat()
    }
    
    payment_manager.create_payment_record(user_data, payment_data)
