from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, create_engine, ForeignKey, Float, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
from dotenv import load_dotenv
import random
import string
import secrets
from database.db import db

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///health_bot.db")
Base = declarative_base()

# Функция для генерации уникального ключа доступа
def generate_access_key(length=16):
    return secrets.token_hex(length)

class MessageHistory(db.Model):
    __tablename__ = 'message_history'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    role = Column(String(20), nullable=False)  # 'user' или 'assistant'
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.now)
    
    # Связь с пользователем определим после объявления класса User
    
    def __repr__(self):
        return f"<MessageHistory(id={self.id}, user_id={self.user_id}, role={self.role})>"

class User(db.Model):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), unique=True, nullable=False)  # Telegram ID
    username = Column(String(100), nullable=True)
    email = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    
    # Данные анкеты
    gender = Column(String(10), nullable=True)
    age = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    weight = Column(Integer, nullable=True)
    main_goal = Column(String(100), nullable=True)
    additional_goal = Column(String(100), nullable=True)
    work_format = Column(String(100), nullable=True)
    sport_frequency = Column(String(100), nullable=True)
    
    # Данные о регистрации и подписке
    registration_date = Column(DateTime, default=datetime.now)
    first_interaction_time = Column(DateTime, default=datetime.now)  # Время первого взаимодействия
    is_subscribed = Column(Boolean, default=False)
    subscription_type = Column(String(20), nullable=True)
    subscription_expires = Column(DateTime, nullable=True)
    
    # Данные о сомнениях при выборе подписки
    subscription_doubt_status = Column(String(50), nullable=True)  # "Показ вариантов", "Дорого", "Насчет результата"
    subscription_doubt_response = Column(String(100), nullable=True)  # Ответ пользователя на сомнение
    subscription_doubt_feedback = Column(Text, nullable=True)  # Обратная связь пользователя после отказа
    
    # Данные об отмене подписки
    cancellation_reason_1 = Column(Text, nullable=True)  # Первая причина отмены
    cancellation_reason_2 = Column(Text, nullable=True)  # Вторая причина отмены
    cancellation_date = Column(DateTime, nullable=True)  # Дата начала процесса отмены
    
    # Реферальные данные
    referral_code = Column(String(20), nullable=True)
    referred_by = Column(String(20), nullable=True)
    
    # Новые поля
    first_name = Column(String(100))
    last_name = Column(String(100))
    chat_id = Column(String(50))
    registered_at = Column(DateTime, default=datetime.now)
    registered = Column(Boolean, default=False)  # Флаг завершения регистрации
    payment_status = Column(String(20), default='pending')
    welcome_message_sent = Column(Boolean, default=False)
    referrer_id = Column(String(50), nullable=True)
    referral_source = Column(String(50), nullable=True)
    blogger_ref_code = Column(String(100), nullable=True)  # Код реферальной ссылки блогера
    health_assistant_first_time = Column(Boolean, default=True)  # Флаг первого использования health ассистента
    
    # Отношения
    payments = relationship("Payment", back_populates="user")
    referral_uses = relationship("ReferralUse", back_populates="user", foreign_keys="ReferralUse.user_id")
    referred_users = relationship("ReferralUse", back_populates="referrer", foreign_keys="ReferralUse.referrer_id")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"

# Определяем отношение после объявления обоих классов
MessageHistory.user = relationship("User", backref="messages")

class ReferralCode(db.Model):
    __tablename__ = 'referral_codes'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    code = Column(String(20), unique=True, nullable=False)
    description = Column(String(100), nullable=True)
    discount_percent = Column(Integer, default=0)
    discount_amount = Column(Float, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=True)
    max_uses = Column(Integer, default=0)  # 0 = unlimited
    
    # Статистика использования
    total_uses = Column(Integer, default=0)
    
    # Отношения
    user = relationship("User")
    uses = relationship("ReferralUse", back_populates="code")

    def __repr__(self):
        return f"<ReferralCode(id={self.id}, code={self.code})>"

class ReferralUse(db.Model):
    __tablename__ = 'referral_uses'
    
    id = Column(Integer, primary_key=True)
    referral_code_id = Column(Integer, ForeignKey('referral_codes.id'), name='referral_code_id')
    user_id = Column(Integer, ForeignKey('users.id'))
    referrer_id = Column(Integer, ForeignKey('users.id'))
    referred_id = Column(Integer, nullable=True)  # Для обратной совместимости
    created_at = Column(DateTime, default=datetime.now, name='used_at')
    status = Column(String(20), nullable=True)  # Для обратной совместимости
    subscription_purchased = Column(Boolean, default=False)
    purchase_date = Column(DateTime, nullable=True)
    reward_processed = Column(Boolean, default=False)
    discount_applied = Column(Float, default=0)
    
    # Для совместимости кода
    @property
    def code_id(self):
        return self.referral_code_id
        
    @code_id.setter
    def code_id(self, value):
        self.referral_code_id = value
        
    @property
    def used_at(self):
        return self.created_at
        
    @used_at.setter
    def used_at(self, value):
        self.created_at = value
    
    code = relationship("ReferralCode", back_populates="uses", foreign_keys=[referral_code_id])
    user = relationship("User", foreign_keys=[user_id])
    referrer = relationship("User", foreign_keys=[referrer_id])
    
    def __repr__(self):
        return f"<ReferralUse(id={self.id}, referral_code_id={self.referral_code_id}, user_id={self.user_id})>"

class AdminUser(db.Model):
    __tablename__ = 'admin_users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True, server_default="1")
    added_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<AdminUser(id={self.id}, username={self.username})>"

class Payment(db.Model):
    __tablename__ = 'payments'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    payment_method = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default='RUB')
    status = Column(String(20), default='pending')
    created_at = Column(DateTime, default=datetime.now)
    paid_at = Column(DateTime, nullable=True)
    subscription_type = Column(String(20), nullable=True)  # monthly или yearly
    
    # Связь с пользователем
    user = relationship("User", back_populates="payments")

    def __repr__(self):
        return f"<Payment(id={self.id}, user_id={self.user_id}, amount={self.amount}, status={self.status})>"

class ChatHistory(db.Model):
    __tablename__ = 'chat_history'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id'))
    role = Column(String(20))  # 'system', 'user', 'assistant'
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.now)

class Blogger(db.Model):
    __tablename__ = 'bloggers'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    telegram_id = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    access_key = Column(String(50), unique=True, nullable=False, default=generate_access_key)
    join_date = Column(DateTime, default=datetime.now)  # Переименовано из created_at
    total_earned = Column(Float, default=0.0)
    total_referrals = Column(Integer, default=0)
    total_conversions = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    # Отношения
    referrals = relationship("BloggerReferral", back_populates="blogger")

    def __repr__(self):
        return f"<Blogger(id={self.id}, name={self.name})>"

class BloggerReferral(db.Model):
    __tablename__ = 'blogger_referrals'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    blogger_id = Column(Integer, ForeignKey('bloggers.id'), nullable=False)
    source = Column(String(100), nullable=True)  # Источник перехода (опционально)
    created_at = Column(DateTime, default=datetime.now)
    converted = Column(Boolean, default=False)
    converted_at = Column(DateTime, nullable=True)
    commission_amount = Column(Float, default=0)
    
    # Отношения
    blogger = relationship("Blogger", back_populates="referrals")

    def __repr__(self):
        return f"<BloggerReferral(id={self.id}, blogger_id={self.blogger_id})>"

class BloggerPayment(db.Model):
    __tablename__ = 'blogger_payments'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    blogger_id = Column(Integer, ForeignKey('bloggers.id'), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String(20), default='pending')  # pending, paid, canceled
    created_at = Column(DateTime, default=datetime.now)
    paid_at = Column(DateTime, nullable=True)
    
    # Отношения
    blogger = relationship("Blogger")

    def __repr__(self):
        return f"<BloggerPayment(id={self.id}, blogger_id={self.blogger_id})>"

class PendingNotification(db.Model):
    __tablename__ = 'pending_notifications'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    message_type = Column(String(50), nullable=False)  # тип сообщения: referral_bonus, subscription_expire, etc.
    data = Column(Text, nullable=True)  # JSON данные для формирования сообщения
    created_at = Column(DateTime, default=datetime.now)
    sent = Column(Boolean, default=False)
    sent_at = Column(DateTime, nullable=True)
    retries = Column(Integer, default=0)
    
    def __repr__(self):
        return f"<PendingNotification(id={self.id}, user_id={self.user_id}, type={self.message_type}, sent={self.sent})>"

# Создание движка и таблиц базы данных
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def init_db():
    db.create_all()

def get_session():
    return Session()
