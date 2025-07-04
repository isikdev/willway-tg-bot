import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'default-secret-key'
    
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///willway.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN') or '7719877297:AAEThbxMJj246SMjwV4x2eAMng8e7i4aofA'
    TELEGRAM_BOT_USERNAME = os.environ.get('TELEGRAM_BOT_USERNAME') or 'willwayapp_bot'
    
    ADMIN_API_KEY = os.environ.get('ADMIN_API_KEY') or 'your-admin-api-key'
    
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'} 