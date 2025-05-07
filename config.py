import os

# Пути к базам данных
DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'database.db')
BLOGGERS_DB_PATH = os.path.join(os.path.dirname(__file__), 'willway_bloggers.db')

# Секретный ключ для Flask (если нужен)
FLASK_SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'default_secret_key') 