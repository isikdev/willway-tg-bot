#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Веб-приложение для личного кабинета блогеров
"""

import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
import json
from datetime import datetime, timedelta
import sys

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализация Flask-приложения
app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('SECRET_KEY', 'willway_bloggers_secret_key')

# Импортируем функции из api_bridge
try:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from api_bridge import (
        verify_blogger_key, get_blogger_stats, get_blogger_referrals,
        get_referral_link, get_earnings
    )
    logger.info("✅ API-функции успешно импортированы")
except Exception as e:
    logger.error(f"❌ Ошибка при импорте API-функций: {str(e)}")
    
    # Создаем заглушки для функций, если импорт не удался
    def verify_blogger_key(access_key):
        logger.warning(f"⚠️ Используется заглушка для verify_blogger_key с ключом {access_key}")
        return {"success": False, "error": "API недоступен"}
    
    def get_blogger_stats(blogger_id, access_key):
        logger.warning(f"⚠️ Используется заглушка для get_blogger_stats с ID {blogger_id}")
        return {"success": False, "error": "API недоступен"}
    
    def get_blogger_referrals(blogger_id, access_key, offset=0, limit=10):
        logger.warning(f"⚠️ Используется заглушка для get_blogger_referrals с ID {blogger_id}")
        return {"success": False, "error": "API недоступен"}
    
    def get_referral_link(blogger_id, access_key):
        logger.warning(f"⚠️ Используется заглушка для get_referral_link с ID {blogger_id}")
        return {"success": False, "error": "API недоступен"}
    
    def get_earnings(blogger_id, access_key):
        logger.warning(f"⚠️ Используется заглушка для get_earnings с ID {blogger_id}")
        return {"success": False, "error": "API недоступен"}

# Декоратор для проверки авторизации
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'blogger_id' not in session or 'access_key' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Главная страница - перенаправление на логин
@app.route('/')
def index():
    if 'blogger_id' in session and 'access_key' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# Страница входа
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    
    if request.method == 'POST':
        access_key = request.form.get('access_key', '').strip()
        
        if not access_key:
            error = 'Пожалуйста, введите ключ доступа'
        else:
            # Проверяем ключ доступа через API
            result = verify_blogger_key(access_key)
            
            if result.get('success'):
                # Сохраняем данные в сессии
                session['blogger_id'] = result.get('blogger_id')
                session['access_key'] = access_key
                session['blogger_name'] = result.get('blogger_name', 'Блогер')
                
                flash('Вы успешно вошли в систему', 'success')
                return redirect(url_for('dashboard'))
            else:
                error = result.get('error', 'Неверный ключ доступа')
    
    return render_template('login.html', error=error)

# Дашборд
@app.route('/dashboard')
@login_required
def dashboard():
    blogger_id = session.get('blogger_id')
    access_key = session.get('access_key')
    
    # Получаем статистику блогера
    stats_result = get_blogger_stats(blogger_id, access_key)
    
    if not stats_result.get('success'):
        flash(stats_result.get('error', 'Ошибка при получении статистики'), 'error')
        stats = {}
        ref_stats = {}
        ref_link = ''
    else:
        stats = stats_result
        ref_stats = stats_result  # Используем те же данные для ref_stats
        # Получаем реферальную ссылку
        ref_link_result = get_referral_link(blogger_id, access_key)
        ref_link = ref_link_result.get('referral_link', '#') if ref_link_result.get('success') else '#'
    
    return render_template(
        'dashboard.html',
        blogger_name=session.get('blogger_name', 'Блогер'),
        stats=stats,
        ref_stats=ref_stats,
        ref_link=ref_link
    )

# Страница с реферальной ссылкой
@app.route('/referral-link')
@login_required
def referral_link():
    blogger_id = session.get('blogger_id')
    access_key = session.get('access_key')
    
    # Получаем реферальную ссылку
    result = get_referral_link(blogger_id, access_key)
    
    if not result.get('success'):
        flash(result.get('error', 'Ошибка при получении реферальной ссылки'), 'error')
        ref_link = '#'
    else:
        ref_link = result.get('referral_link', '#')
    
    # Получаем статистику для отображения
    stats_result = get_blogger_stats(blogger_id, access_key)
    ref_stats = stats_result if stats_result.get('success') else {}
    
    return render_template(
        'referral_link.html',
        blogger_name=session.get('blogger_name', 'Блогер'),
        ref_link=ref_link,
        ref_stats=ref_stats
    )

# Страница со списком рефералов
@app.route('/referrals')
@login_required
def referrals():
    blogger_id = session.get('blogger_id')
    access_key = session.get('access_key')
    
    # Получаем список рефералов
    result = get_blogger_referrals(blogger_id, access_key)
    
    if not result.get('success'):
        flash(result.get('error', 'Ошибка при получении списка рефералов'), 'error')
        referrals_list = []
    else:
        referrals_list = result.get('referrals', [])
    
    return render_template(
        'referrals.html',
        blogger_name=session.get('blogger_name', 'Блогер'),
        referrals=referrals_list
    )

# Страница с заработком
@app.route('/earnings')
@login_required
def earnings():
    blogger_id = session.get('blogger_id')
    access_key = session.get('access_key')
    
    # Получаем данные о заработке
    result = get_earnings(blogger_id, access_key)
    
    if not result.get('success'):
        flash(result.get('error', 'Ошибка при получении данных о заработке'), 'error')
        earnings_data = {}
    else:
        earnings_data = result
    
    return render_template(
        'earnings.html',
        blogger_name=session.get('blogger_name', 'Блогер'),
        earnings_data=earnings_data
    )

# Выход из системы
@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))

# Обработка ошибок
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=True) 