from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///health_bot.db")
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(255))
    email = Column(String(255))
    phone = Column(String(20))
    password = Column(String(255))
    gender = Column(String(10))
    age = Column(Integer)
    height = Column(Integer)
    weight = Column(Integer)
    main_goal = Column(String(255))
    additional_goal = Column(String(255))
    work_format = Column(String(255))
    sport_frequency = Column(String(50))
    registration_date = Column(DateTime, default=datetime.now)
    is_subscribed = Column(Boolean, default=False)
    subscription_type = Column(String(20))  # "monthly" или "yearly"
    subscription_expires = Column(DateTime)
    is_admin = Column(Boolean, default=False)  # Устаревшее поле, оставлено для обратной совместимости
    registered = Column(Boolean, default=False)
    airtable_synced = Column(Boolean, default=False)
    
    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"

class AdminUser(Base):
    __tablename__ = 'admin_users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(255))
    added_at = Column(DateTime, default=datetime.now)
    
    def __repr__(self):
        return f"<AdminUser(id={self.id}, user_id={self.user_id}, username={self.username})>"

# Создание движка и таблиц базы данных
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)

def get_session():
    return Session()
