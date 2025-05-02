import os
import sys
import logging
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Float, MetaData, Table
from datetime import datetime
from dotenv import load_dotenv
import sqlalchemy as sa

# Добавляем корневую директорию проекта в путь импорта
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

# Получаем URL базы данных из переменных окружения
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///health_bot.db")

# Создаем движок для работы с базой данных
engine = create_engine(DATABASE_URL)
metadata = MetaData()

def create_referral_tables():
    try:
        # Проверяем существование таблицы referral_codes
        inspector = sa.inspect(engine)
        if 'referral_codes' in inspector.get_table_names():
            # Таблица уже существует, проверяем схему
            conn = engine.connect()
            columns = [col['name'] for col in inspector.get_columns('referral_codes')]
            
            # Добавляем столбец user_id, если его нет
            if 'user_id' not in columns:
                logger.info("Добавляем столбец user_id в таблицу referral_codes")
                conn.execute(sa.text('ALTER TABLE referral_codes ADD COLUMN user_id INTEGER'))
            
            # Проверяем наличие колонок и структуру таблицы
            if 'is_active' not in columns:
                # Создаем временную таблицу для сохранения данных
                conn.execute(sa.text('CREATE TABLE IF NOT EXISTS referral_codes_temp AS SELECT * FROM referral_codes'))
                conn.execute(sa.text('DROP TABLE referral_codes'))
                logger.info("Существующая таблица referral_codes преобразована во временную")
            
            # Создаем таблицу с новой структурой
            referral_codes = Table(
                'referral_codes',
                metadata,
                Column('id', Integer, primary_key=True, autoincrement=True),
                Column('user_id', Integer, ForeignKey('users.id'), nullable=True),
                Column('code', String(20), unique=True, nullable=False),
                Column('description', String(100), nullable=True),
                Column('discount_percent', Integer, default=0),
                Column('discount_amount', Float, default=0),
                Column('is_active', Boolean, default=True),
                Column('created_at', DateTime, default=datetime.now),
                Column('expires_at', DateTime, nullable=True),
                Column('max_uses', Integer, default=0),
                Column('total_uses', Integer, default=0)
            )
            metadata.create_all(engine, tables=[referral_codes])
            
            # Восстанавливаем данные, если была временная таблица
            if conn.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name='referral_codes_temp'")).fetchone():
                logger.info("Восстанавливаем данные из временной таблицы")
                # Получаем список столбцов для обеих таблиц
                temp_columns = [col['name'] for col in inspector.get_columns('referral_codes_temp')]
                new_columns = [col['name'] for col in inspector.get_columns('referral_codes')]
                
                # Находим общие столбцы
                common_columns = [col for col in temp_columns if col in new_columns]
                columns_str = ", ".join(common_columns)
                
                # Копируем данные из временной таблицы
                conn.execute(sa.text(f"INSERT INTO referral_codes ({columns_str}) SELECT {columns_str} FROM referral_codes_temp"))
                conn.execute(sa.text("DROP TABLE referral_codes_temp"))
                logger.info("Данные из временной таблицы восстановлены, временная таблица удалена")
            
            logger.info("Таблица referral_codes обновлена с новой структурой")
        else:
            # Создаем таблицу referral_codes с новой структурой
            referral_codes = Table(
                'referral_codes',
                metadata,
                Column('id', Integer, primary_key=True, autoincrement=True),
                Column('user_id', Integer, ForeignKey('users.id'), nullable=True),
                Column('code', String(20), unique=True, nullable=False),
                Column('description', String(100), nullable=True),
                Column('discount_percent', Integer, default=0),
                Column('discount_amount', Float, default=0),
                Column('is_active', Boolean, default=True),
                Column('created_at', DateTime, default=datetime.now),
                Column('expires_at', DateTime, nullable=True),
                Column('max_uses', Integer, default=0),
                Column('total_uses', Integer, default=0)
            )
            metadata.create_all(engine, tables=[referral_codes])
            logger.info("Таблица referral_codes создана")
        
        # Создаем таблицу referral_uses, если она не существует
        referral_uses = Table(
            'referral_uses',
            metadata,
            Column('id', Integer, primary_key=True, autoincrement=True),
            Column('referral_code_id', Integer, ForeignKey('referral_codes.id'), nullable=False),
            Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
            Column('referrer_id', Integer, nullable=True),
            Column('used_at', DateTime, default=datetime.now),
            Column('discount_applied', Float, default=0),
            Column('subscription_purchased', Boolean, default=False),
            Column('purchase_date', DateTime, nullable=True)
        )
        
        # Создаем таблицы в базе данных
        metadata.create_all(engine, tables=[referral_uses])
        logger.info("Таблица referral_uses создана или обновлена")
        return True
    except Exception as e:
        logger.error(f"Ошибка при создании или обновлении таблиц реферальной системы: {str(e)}")
        return False

def add_referral_fields_to_users():
    try:
        conn = engine.connect()
        
        # Проверяем наличие колонок перед добавлением
        inspector = sa.inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('users')]
        
        if 'referrer_id' not in columns:
            conn.execute(sa.text('ALTER TABLE users ADD COLUMN referrer_id INTEGER'))
            logger.info("Колонка referrer_id добавлена в таблицу users")
        
        if 'referral_source' not in columns:
            conn.execute(sa.text('ALTER TABLE users ADD COLUMN referral_source VARCHAR(20) DEFAULT "direct"'))
            logger.info("Колонка referral_source добавлена в таблицу users")
        
        if 'first_interaction_time' not in columns:
            conn.execute(sa.text('ALTER TABLE users ADD COLUMN first_interaction_time DATETIME DEFAULT CURRENT_TIMESTAMP'))
            logger.info("Колонка first_interaction_time добавлена в таблицу users")
        
        # Добавляем колонки referral_code и referred_by, если их нет
        if 'referral_code' not in columns:
            conn.execute(sa.text('ALTER TABLE users ADD COLUMN referral_code VARCHAR(20)'))
            logger.info("Колонка referral_code добавлена в таблицу users")
        
        if 'referred_by' not in columns:
            conn.execute(sa.text('ALTER TABLE users ADD COLUMN referred_by VARCHAR(20)'))
            logger.info("Колонка referred_by добавлена в таблицу users")
        
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка при добавлении полей в таблицу users: {str(e)}")
        return False

def update_admin_users_table():
    try:
        conn = engine.connect()
        inspector = sa.inspect(engine)
        
        # Проверяем существование таблицы admin_users
        if 'admin_users' not in inspector.get_table_names():
            # Создаем таблицу admin_users
            admin_users = Table(
                'admin_users',
                metadata,
                Column('id', Integer, primary_key=True, autoincrement=True),
                Column('username', String(50), unique=True, nullable=False),
                Column('password', String(100), nullable=False),
                Column('is_active', Boolean, default=True)
            )
            metadata.create_all(engine, tables=[admin_users])
            logger.info("Таблица admin_users создана")
            
            # Добавляем админа по умолчанию
            conn.execute(sa.text("INSERT INTO admin_users (username, password, is_active) VALUES ('admin', '123', 1)"))
            logger.info("Добавлен пользователь admin по умолчанию")
        else:
            # Проверяем наличие колонок
            columns = [col['name'] for col in inspector.get_columns('admin_users')]
            
            if 'password' not in columns:
                conn.execute(sa.text('ALTER TABLE admin_users ADD COLUMN password VARCHAR(100)'))
                logger.info("Колонка password добавлена в таблицу admin_users")
                
                # Обновляем пароль по умолчанию для всех существующих записей
                conn.execute(sa.text("UPDATE admin_users SET password = '123' WHERE password IS NULL"))
                logger.info("Пароль по умолчанию '123' установлен для всех существующих админов")
            
            if 'is_active' not in columns:
                conn.execute(sa.text('ALTER TABLE admin_users ADD COLUMN is_active BOOLEAN DEFAULT 1'))
                logger.info("Колонка is_active добавлена в таблицу admin_users")
        
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка при обновлении таблицы admin_users: {str(e)}")
        return False

def check_bloggers_flask_app():
    try:
        # Создаем файл с инициализацией Flask и SQLAlchemy для блогеров
        init_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'willway_blogers', '__init__.py')
        
        if not os.path.exists(os.path.dirname(init_file_path)):
            os.makedirs(os.path.dirname(init_file_path))
            logger.info(f"Создана директория {os.path.dirname(init_file_path)}")
        
        if not os.path.exists(init_file_path):
            with open(init_file_path, 'w') as f:
                f.write("""from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL", "sqlite:///health_bot.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")

db = SQLAlchemy(app)

from willway_blogers import routes
""")
            logger.info(f"Создан инициализационный файл для блогеров: {init_file_path}")
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при настройке Flask-приложения блогеров: {str(e)}")
        return False

def create_all_tables():
    """Создает все необходимые таблицы из моделей SQLAlchemy"""
    try:
        # Импортируем здесь, чтобы избежать циклического импорта
        from database.db import db
        from database.models import User, ReferralCode, ReferralUse, AdminUser, Blogger, BloggerReferral, BloggerPayment, Payment
        
        # Создаем движок SQLAlchemy и соединение с базой данных
        from flask import Flask
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        # Привязываем приложение к db
        db.init_app(app)
        
        # Создаем все таблицы в контексте приложения
        with app.app_context():
            logger.info("Создаем все таблицы из моделей SQLAlchemy...")
            db.create_all()
            logger.info("Все таблицы успешно созданы")
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при создании таблиц: {str(e)}")
        return False

def run_migrations():
    try:
        # Сначала создаем все таблицы из моделей
        create_all_tables()
        
        # Добавляем поля в таблицу пользователей
        add_referral_fields_to_users()
        
        # Обновляем таблицу admin_users
        update_admin_users_table()
        
        # Обновляем таблицы реферальной системы
        create_referral_tables()
        
        # Проверяем настройку Flask app для блогеров
        check_bloggers_flask_app()
        
        logger.info("Миграции успешно выполнены")
        return True
    except Exception as e:
        logger.error(f"Ошибка при выполнении миграций: {str(e)}")
        return False

if __name__ == "__main__":
    run_migrations() 