#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from datetime import datetime
from database.models import init_db
from web_admin.app import app

# Инициализируем БД
init_db()

# Добавляем функцию now для работы в шаблонах
@app.context_processor
def utility_processor():
    def now():
        return datetime.now()
    return dict(now=now)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5001, debug=True)
