#!/usr/bin/env python
import os
import sys
from flask_migrate import Migrate, MigrateCommand
from flask_script import Manager

# Обеспечиваем корректный путь для импортов
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

# Импортируем приложение Flask и базу данных
from web_admin.app import app
from database.db import db

# Инициализируем миграции
migrate = Migrate(app, db)
manager = Manager(app)
manager.add_command('db', MigrateCommand)

if __name__ == "__main__":
    manager.run() 