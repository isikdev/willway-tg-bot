import os
import sys
import secrets
from datetime import datetime, timedelta

# Добавляем корневую директорию проекта в sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

from database.db import db
from database.models import Blogger, BloggerReferral, User, generate_access_key

def create_test_data():
    """Создание тестовых данных для демонстрации"""
    
    # Проверяем, есть ли уже тестовые данные
    if Blogger.query.count() > 0:
        print("Тестовые данные уже существуют")
        return
    
    # Создаем тестового блогера
    test_blogger = Blogger(
        name="Тестовый Блогер",
        telegram_id="123456789",
        email="test@example.com",
        access_key="testkey123456",
        created_at=datetime.now() - timedelta(days=30)
    )
    db.session.add(test_blogger)
    db.session.flush()  # Получаем ID блогера
    
    # Создаем тестовые переходы по реферальной ссылке
    for i in range(30):
        # Создаем записи за последние 30 дней
        created_date = datetime.now() - timedelta(days=30-i)
        
        # Создаем от 0 до 5 переходов на каждый день
        for j in range(min(5, i % 7 + 1)):
            referral = BloggerReferral(
                blogger_id=test_blogger.id,
                source=f"source_{j}",
                created_at=created_date,
                converted=j % 3 == 0,  # Каждый третий переход приводит к конверсии
                commission_amount=j % 3 == 0 and 500 or 0  # 500 рублей за конверсию
            )
            if referral.converted:
                referral.converted_at = referral.created_at + timedelta(hours=2)
            
            db.session.add(referral)
    
    # Создаем тестового пользователя-администратора
    admin_user = User(
        user_id="admin123",
        username="Admin",
        email="admin@example.com",
        is_subscribed=True,
        subscription_type="premium",
        subscription_expires=datetime.now() + timedelta(days=365)
    )
    db.session.add(admin_user)
    
    # Сохраняем изменения
    db.session.commit()
    print("Тестовые данные успешно созданы")

def init_db():
    """Инициализация базы данных"""
    print("Инициализация базы данных...")
    from web_admin.app import app
    
    with app.app_context():
        # Создаем все таблицы
        db.create_all()
        print("База данных успешно инициализирована")
        
        # Создаем тестовые данные
        create_test_data()
    
    print("Готово!")

if __name__ == "__main__":
    init_db() 