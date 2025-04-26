import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'default-secret-key'
    
    # Настройки базы данных
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///willway.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Настройки Telegram
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN') or '7740860872:AAGUyww-0gQox8ucDk90rSsoQdz-J-lqkug'
    TELEGRAM_BOT_USERNAME = os.environ.get('TELEGRAM_BOT_USERNAME') or 'WILLWAY_ReferalBot'
    
    # Настройки для API
    ADMIN_API_KEY = os.environ.get('ADMIN_API_KEY') or 'your-admin-api-key'
    
    # Настройки для загрузки файлов
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'} 