from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Blueprint
from functools import wraps
import os
from datetime import datetime, timedelta
import calendar
from sqlalchemy import func, extract, text
from database.models import get_session, User, AdminUser, ReferralCode, ReferralUse, Blogger, BloggerReferral, BloggerPayment, generate_access_key, Payment
from dotenv import load_dotenv
import json
import requests
from werkzeug.utils import secure_filename
from database.db import db, init_flask_db
from flask_migrate import Migrate
from web_admin.api_routes import api_bp
from web_admin.blogger_utils import *

# Система платежей отключена
# Создаем пустой blueprint для совместимости
payment_routes = Blueprint('payment_routes', __name__)
print("Система оплаты отключена.")

import logging
import sys

# Добавляем корневую директорию проекта в sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'img')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Настройка базы данных
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///health_bot.db")
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['DB_FOLDER'] = os.path.dirname(os.path.abspath(__file__))  # Добавляем путь к папке с базами данных

# Инициализация базы данных с помощью функции из database.db
init_flask_db(app)
migrate = Migrate(app, db)

# Регистрируем api_blueprint с правильным префиксом
app.register_blueprint(api_bp)

# Добавляем контекстный процессор для передачи bot_username во все шаблоны
@app.context_processor
def inject_bot_username():
    logging.info("Инициализация контекстного процессора bot_username")
    return {'bot_username': os.getenv('TELEGRAM_BOT_USERNAME', 'willwayapp_bot')}

# Добавляем инструмент для работы с типами в шаблонах
@app.context_processor
def inject_types():
    logging.info("Инициализация контекстного процессора типов - добавляем string и hasattr в контекст")
    
    # Функция для безопасного форматирования даты
    def format_date(date_value, format_str='%d.%m.%Y %H:%M'):
        if date_value is None:
            return "Нет данных"
        if isinstance(date_value, str):
            return date_value
        try:
            return date_value.strftime(format_str)
        except (AttributeError, ValueError, TypeError):
            return str(date_value)
    
    return {
        'string': str, 
        'hasattr': hasattr,
        'format_date': format_date
    }

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация для Telegram бота
app.config['TELEGRAM_BOT_TOKEN'] = os.getenv("TELEGRAM_BOT_TOKEN", "")
app.config['TELEGRAM_BOT_USERNAME'] = os.getenv("TELEGRAM_BOT_USERNAME", "willwayapp_bot")
app.config['ADMIN_API_KEY'] = os.getenv("ADMIN_API_KEY", "admin_secret_key")

# Данные для авторизации из .env файла
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "123")

# Путь к файлу конфигурации бота
BOT_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bot_config.json')

# Проверка допустимых расширений файлов
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Декоратор для проверки авторизации
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Маршруты для авторизации
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Неверное имя пользователя или пароль', 'error')
    
    return render_template('admin/login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# Маршрут для главной страницы админки (аналитика)
@app.route('/')
def admin_root():
    """Обработка запросов в зависимости от поддомена"""
    host = request.host.lower()
    
    if 'admin.api-willway.ru' in host:
        if 'logged_in' in session:
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('login'))
    elif 'bloggers.api-willway.ru' in host:
        # Используем прямой URL вместо url_for, чтобы избежать проблем с поддоменами
        return redirect('/blogger/login')
    else:
        return "Willway Admin API"

# Добавляем отдельный маршрут для панели администратора
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    """Отображение панели администратора"""
    db_session = get_session()
    
    # Получаем текущий месяц и год
    current_date = datetime.now()
    current_month = current_date.month
    current_year = current_date.year
    
    # Получаем статистику по регистрациям за текущий месяц
    registrations_this_month = db_session.query(User).filter(
        extract('month', User.registration_date) == current_month,
        extract('year', User.registration_date) == current_year
    ).count()
    
    # Получаем статистику по подпискам за текущий месяц
    subscriptions_this_month = db_session.query(User).filter(
        User.is_subscribed == True,
        extract('month', User.subscription_expires) >= current_month,
        extract('year', User.subscription_expires) >= current_year
    ).count()
    
    # Получаем реальные данные о регистрациях по месяцам за текущий год
    monthly_registrations_data = db_session.query(
        extract('month', User.registration_date).label('month'),
        func.count().label('count')
    ).filter(
        extract('year', User.registration_date) == current_year
    ).group_by(
        extract('month', User.registration_date)
    ).all()
    
    # Получаем реальные данные о подписках по месяцам за текущий год
    monthly_subscriptions_data = db_session.query(
        extract('month', User.subscription_expires).label('month'),
        func.count().label('count')
    ).filter(
        User.is_subscribed == True,
        extract('year', User.subscription_expires) == current_year
    ).group_by(
        extract('month', User.subscription_expires)
    ).all()
    
    # Преобразуем данные в формат для графиков
    monthly_registrations = []
    monthly_subscriptions = []
    
    for month in range(1, 13):
        month_name = calendar.month_name[month]
        
        # Находим соответствующие данные по регистрациям для месяца
        reg_count = 0
        for data in monthly_registrations_data:
            if int(data.month) == month:
                reg_count = data.count
                break
                
        # Находим соответствующие данные по подпискам для месяца
        sub_count = 0
        for data in monthly_subscriptions_data:
            if int(data.month) == month:
                sub_count = data.count
                break
        
        monthly_registrations.append({'month': month_name, 'count': reg_count})
        monthly_subscriptions.append({'month': month_name, 'count': sub_count})
    
    # Рассчитываем конверсию
    conversion_rate = 0
    if registrations_this_month > 0:
        conversion_rate = (subscriptions_this_month / registrations_this_month) * 100
    
    # Рассчитываем приблизительный доход
    # Используем цену из переменной окружения или значение по умолчанию
    subscription_price = int(os.environ.get('MONTHLY_SUBSCRIPTION_PRICE', 990))
    monthly_revenue = subscriptions_this_month * subscription_price
    
    db_session.close()
    
    return render_template('admin/dashboard.html', 
                          registrations_this_month=registrations_this_month,
                          subscriptions_this_month=subscriptions_this_month,
                          monthly_registrations=monthly_registrations,
                          monthly_subscriptions=monthly_subscriptions,
                          conversion_rate=conversion_rate,
                          monthly_revenue=monthly_revenue)

# Маршрут для страницы с таблицей пользователей
@app.route('/users')
@login_required
def users():
    db_session = get_session()
    all_users = db_session.query(User).all()
    db_session.close()
    
    return render_template('admin/users.html', users=all_users)

# Маршрут для получения данных пользователя по API
@app.route('/api/user/<int:user_id>', methods=['GET'])
@login_required
def get_user_details(user_id):
    db_session = get_session()
    user = db_session.query(User).filter(User.id == user_id).first()
    
    if not user:
        db_session.close()
        return jsonify({'error': 'Пользователь не найден'}), 404
    
    # Формируем информацию об отмене подписки в отдельный объект
    cancellation_info = {
        'cancellation_date': user.cancellation_date.isoformat() if hasattr(user, 'cancellation_date') and user.cancellation_date else None,
        'cancellation_reason_1': user.cancellation_reason_1 if hasattr(user, 'cancellation_reason_1') else None,
        'cancellation_reason_2': user.cancellation_reason_2 if hasattr(user, 'cancellation_reason_2') else None,
        'cancellation_additional_comment': user.cancellation_additional_comment if hasattr(user, 'cancellation_additional_comment') else None
    }
    
    user_data = {
        'id': user.id,
        'telegram_id': user.user_id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'phone': user.phone,
        'gender': user.gender,
        'age': user.age,
        'height': user.height,
        'weight': user.weight,
        'main_goal': user.main_goal,
        'additional_goal': user.additional_goal,
        'work_format': user.work_format,
        'sport_frequency': user.sport_frequency,
        'registration_date': user.registration_date.isoformat() if user.registration_date else None,
        'is_subscribed': user.is_subscribed,
        'subscription_type': user.subscription_type,
        'subscription_expires': user.subscription_expires.isoformat() if user.subscription_expires else None,
        'cancellation_info': cancellation_info
    }
    
    db_session.close()
    return jsonify(user_data)

# Маршрут для обновления данных пользователя
@app.route('/api/user/<int:user_id>/update', methods=['POST'])
@login_required
def update_user(user_id):
    db_session = get_session()
    user = db_session.query(User).filter(User.id == user_id).first()
    
    if not user:
        db_session.close()
        return jsonify({'error': 'Пользователь не найден'}), 404
    
    # Обновляем данные пользователя
    user.username = request.form.get('username', user.username)
    user.gender = request.form.get('gender', user.gender)
    
    # Преобразование числовых значений
    try:
        age = request.form.get('age')
        if age:
            user.age = int(age)
    except ValueError:
        pass
    
    try:
        height = request.form.get('height')
        if height:
            user.height = int(height)
    except ValueError:
        pass
    
    try:
        weight = request.form.get('weight')
        if weight:
            user.weight = int(weight)
    except ValueError:
        pass
    
    user.main_goal = request.form.get('main_goal', user.main_goal)
    user.additional_goal = request.form.get('additional_goal', user.additional_goal)
    user.work_format = request.form.get('work_format', user.work_format)
    user.sport_frequency = request.form.get('sport_frequency', user.sport_frequency)
    
    db_session.commit()
    db_session.close()
    
    return jsonify({'success': True, 'message': 'Данные пользователя успешно обновлены'})

# Маршрут для сброса подписки пользователя
@app.route('/api/user/<int:user_id>/reset-subscription', methods=['POST'])
@login_required
def reset_subscription(user_id):
    db_session = get_session()
    user = db_session.query(User).filter(User.id == user_id).first()
    
    if not user:
        db_session.close()
        return jsonify({'error': 'Пользователь не найден'}), 404
    
    # Сбрасываем подписку
    user.is_subscribed = False
    user.subscription_type = None
    user.subscription_expires = None
    
    db_session.commit()
    db_session.close()
    
    return jsonify({'success': True, 'message': 'Подписка пользователя успешно сброшена'})

# Маршрут для удаления пользователя
@app.route('/api/user/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    db_session = get_session()
    try:
        user = db_session.query(User).filter(User.id == user_id).first()
        
        if not user:
            db_session.close()
            return jsonify({'error': 'Пользователь не найден'}), 404
        
        # Сначала удаляем связанные платежи
        db_session.query(Payment).filter(Payment.user_id == user_id).delete()
        
        # Удаляем связанные реферальные использования
        db_session.query(ReferralUse).filter(
            (ReferralUse.user_id == user_id) | (ReferralUse.referrer_id == user_id)
        ).delete()
        
        # Удаляем реферальные коды пользователя
        db_session.query(ReferralCode).filter(ReferralCode.user_id == user_id).delete()
        
        # Удаляем пользователя
        db_session.delete(user)
        db_session.commit()
        return jsonify({'success': True, 'message': 'Пользователь успешно удален'})
    except Exception as e:
        db_session.rollback()
        app.logger.error(f"Ошибка при удалении пользователя: {str(e)}")
        return jsonify({'error': f'Ошибка при удалении пользователя: {str(e)}'}), 500
    finally:
        db_session.close()

# Маршрут для страницы рассылки
@app.route('/message-sender', methods=['GET', 'POST'])
@login_required
def message_sender():
    db_session = get_session()
    all_users = db_session.query(User).all()
    
    if request.method == 'POST':
        message_text = request.form.get('message_text')
        button_text = request.form.get('button_text', '')
        button_url = request.form.get('button_url', '')
        recipients = request.form.getlist('recipients')
        
        # Здесь будет логика отправки сообщений через API Telegram
        # В реальном проекте это должно быть подключено к вашему боту
        
        flash('Сообщение успешно отправлено выбранным пользователям', 'success')
        return redirect(url_for('message_sender'))
    
    db_session.close()
    return render_template('admin/message_sender.html', users=all_users)

# Маршрут для страницы настроек бота
@app.route('/bot-settings', methods=['GET', 'POST'])
@login_required
def bot_settings():
    # Значения по умолчанию
    default_config = {
        "bot_token": "",
        "bot_name": "WillWay Bot",
        "about_text": "",
        "description": "",
        "privacy_mode": False,
        "trainer_username": "",
        "manager_username": "",
        "channel_url": "https://t.me/willway_channel",
        "subscription_page_url": "https://willway.ru/subscriptions",
        "reviews_page_url": "https://willway.ru/reviews",
        "test_drive_url": "https://willway.ru/test-drive",
        "commands": {
            "/start": "Начать общение с ботом",
            "/help": "Показать справку"
        }
    }
    
    # Проверяем существование файла конфигурации
    if os.path.exists(BOT_CONFIG_FILE):
        try:
            with open(BOT_CONFIG_FILE, 'r', encoding='utf-8') as f:
                current_config = json.load(f)
                
                # Проверяем наличие всех необходимых ключей и добавляем отсутствующие из default_config
                for key, value in default_config.items():
                    if key not in current_config:
                        current_config[key] = value
        except Exception as e:
            flash(f'Ошибка при чтении файла конфигурации: {str(e)}', 'error')
            current_config = default_config
    else:
        # Если файл не существует, используем значения по умолчанию
        current_config = default_config
        # Создаем файл с настройками по умолчанию
        try:
            with open(BOT_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            flash(f'Ошибка при создании файла конфигурации: {str(e)}', 'error')
    
    # Получаем список администраторов для отображения в шаблоне
    db_session = get_session()
    admins = db_session.query(AdminUser).all()
    
    # Получаем список обычных пользователей для добавления в админы
    admin_usernames = [admin.username for admin in admins]
    non_admin_users = db_session.query(User).filter(~User.username.in_(admin_usernames) if admin_usernames else True).limit(10).all()
    
    if request.method == 'POST':
        action = request.form.get('action', '')
        
        # Обработка действий с администраторами
        if action == 'add_admin':
            username = request.form.get('username', '')
            password = request.form.get('password', '')
            
            if not username or not password:
                flash('Имя пользователя и пароль обязательны', 'error')
            else:
                try:
                    db_session = get_session()
                    # Проверяем, не существует ли уже админ с таким именем
                    existing_admin = db_session.query(AdminUser).filter(AdminUser.username == username).first()
                    
                    if existing_admin:
                        flash(f'Администратор с именем {username} уже существует', 'warning')
                    else:
                        # Добавляем нового админа
                        new_admin = AdminUser(username=username, password=password)
                        db_session.add(new_admin)
                        db_session.commit()
                        flash(f'Администратор {username} успешно добавлен', 'success')
                    db_session.close()
                except Exception as e:
                    flash(f'Ошибка при добавлении администратора: {str(e)}', 'error')
            
            return redirect(url_for('bot_settings'))
            
        elif action == 'remove_admin':
            admin_id = request.form.get('admin_id')
            
            if not admin_id:
                flash('ID администратора не указан', 'error')
            else:
                try:
                    db_session = get_session()
                    admin = db_session.query(AdminUser).filter(AdminUser.id == admin_id).first()
                    if admin:
                        db_session.delete(admin)
                        db_session.commit()
                        flash(f'Администратор {admin.username} успешно удален', 'success')
                    else:
                        flash('Администратор не найден', 'error')
                    db_session.close()
                except Exception as e:
                    flash(f'Ошибка при удалении администратора: {str(e)}', 'error')
            
            return redirect(url_for('bot_settings'))
            
        else:  # Обработка настроек бота
            try:
                # Создаем директорию для загрузки файлов, если она не существует
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                
                # Обновляем конфигурацию из формы
                updated_config = {
                    "bot_token": request.form.get('bot_token', default_config["bot_token"]),
                    "bot_name": request.form.get('bot_name', default_config["bot_name"]),
                    "about_text": request.form.get('about_text', default_config.get("about_text", "")),
                    "description": request.form.get('description', default_config.get("description", "")),
                    "privacy_mode": 'privacy_mode' in request.form,
                    "trainer_username": request.form.get('trainer_username', default_config.get("trainer_username", "")),
                    "manager_username": request.form.get('manager_username', default_config.get("manager_username", "")),
                    "channel_url": request.form.get('channel_url', default_config.get("channel_url", "https://t.me/willway_channel")),
                    "subscription_page_url": request.form.get('subscription_page_url', default_config.get("subscription_page_url", "https://willway.ru/subscriptions")),
                    "reviews_page_url": request.form.get('reviews_page_url', default_config.get("reviews_page_url", "https://willway.ru/reviews")),
                    "test_drive_url": request.form.get('test_drive_url', default_config.get("test_drive_url", "https://willway.ru/test-drive")),
                    "description_pic_url": current_config.get("description_pic_url", ""),
                    "botpic_url": current_config.get("botpic_url", ""),
                    "intro_video_url": current_config.get("intro_video_url", ""),
                    "commands": current_config.get("commands", default_config["commands"])
                }
                
                # Обрабатываем команды бота
                commands = {}
                cmd_names = request.form.getlist('cmd_name[]')
                cmd_descs = request.form.getlist('cmd_desc[]')
                
                for i in range(len(cmd_names)):
                    if cmd_names[i] and cmd_descs[i]:  # Добавляем только непустые команды
                        commands[cmd_names[i]] = cmd_descs[i]
                
                # Если команд нет, используем значения по умолчанию
                if not commands:
                    commands = default_config["commands"]
                
                updated_config["commands"] = commands
                
                # Сохраняем обновленную конфигурацию в файл
                with open(BOT_CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(updated_config, f, ensure_ascii=False, indent=4)
                
                flash('Настройки бота успешно обновлены', 'success')
                
            except Exception as e:
                flash(f'Ошибка при сохранении настроек: {str(e)}', 'error')
            
            return redirect(url_for('bot_settings'))
    
    return render_template('admin/bot_settings.html', config=current_config, admins=admins, non_admin_users=non_admin_users)

# API для получения информации о боте по токену
@app.route('/api/check-bot-token', methods=['POST'])
@login_required
def check_bot_token():
    token = request.json.get('token', '')
    
    if not token:
        return jsonify({'success': False, 'error': 'Токен не указан'})
    
    try:
        response = requests.get(f"https://api.telegram.org/bot{token}/getMe")
        if response.status_code == 200:
            bot_info = response.json()
            if bot_info["ok"]:
                return jsonify({
                    'success': True, 
                    'bot_info': {
                        'id': bot_info['result']['id'],
                        'name': bot_info['result']['first_name'],
                        'username': bot_info['result']['username']
                    }
                })
        
        return jsonify({'success': False, 'error': 'Недействительный токен'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Маршрут для страницы рефералок
@app.route('/referrals')
@login_required
def referrals():
    try:
        # Логирование начала выполнения
        logging.info("Начало выполнения функции referrals()")
        db_session = get_session()
        
        # Проверяем соединение с базой данных
        logging.info("Проверка соединения с БД")
        try:
            from sqlalchemy.sql import text
            db_session.execute(text("SELECT 1"))
            logging.info("Соединение с БД успешно")
        except Exception as e:
            logging.error(f"Ошибка соединения с БД: {str(e)}")
            flash(f'Ошибка соединения с базой данных: {str(e)}', 'error')
            
            # Определяем вспомогательную функцию для форматирования дат
            def format_date(date_value, format_str='%d.%m.%Y %H:%M'):
                if date_value is None:
                    return "Нет данных"
                if isinstance(date_value, str):
                    return date_value
                try:
                    return date_value.strftime(format_str)
                except (AttributeError, ValueError, TypeError):
                    return str(date_value)
            
            return render_template('admin/referrals.html', 
                           referral_codes=[],
                           referral_uses=[],
                           total_referral_codes=0,
                           total_referral_uses=0,
                           total_paid=0,
                           conversion_rate=0,
                           string=str,
                           hasattr=hasattr,
                           format_date=format_date)  # Передаем функцию форматирования дат в контекст
        
        try:
            # Получаем все реферальные коды
            referral_codes = db_session.query(ReferralCode).all()
            print(f"Получено {len(referral_codes)} реферальных кодов")
            
            # Преобразуем результаты в удобный формат для шаблона
            referrals_data = []
            for code in referral_codes:
                try:
                    # Получаем количество использований этого кода
                    referral_count = db_session.query(ReferralUse).filter(
                        ReferralUse.referral_code_id == code.id
                    ).count()
                    
                    # Получаем количество оплаченных подписок
                    paid_count = db_session.query(ReferralUse).filter(
                        ReferralUse.referral_code_id == code.id,
                        ReferralUse.subscription_purchased == True
                    ).count()
                except Exception as e:
                    # Если колонки еще нет, считаем что количество использований 0
                    referral_count = 0
                    paid_count = 0
                    print(f"Ошибка при подсчете использований реферального кода: {str(e)}")
                    
                # Добавляем информацию о пользователе
                user = None
                username = "Неизвестно"
                if code.user_id:
                    try:
                        user = db_session.query(User).filter(User.id == code.user_id).first()
                        if not user:
                            # Если не нашли по ID, пробуем найти по Telegram ID (для обратной совместимости)
                            user = db_session.query(User).filter(User.user_id == code.user_id).first()
                            
                        if user:
                            username = user.username or str(user.user_id) or "Неизвестно"
                    except Exception as e:
                        print(f"Ошибка при получении данных пользователя: {str(e)}")
                        
                # Проверяем наличие атрибута is_active
                is_active = False
                try:
                    is_active = code.is_active if hasattr(code, 'is_active') else (code.active if hasattr(code, 'active') else False)
                except Exception as e:
                    print(f"Ошибка при определении активности кода: {str(e)}")
                    
                # Проверяем тип created_at и преобразуем его в строку, если это объект datetime
                created_at = None
                if hasattr(code, 'created_at'):
                    try:
                        if code.created_at and not isinstance(code.created_at, str):
                            created_at = code.created_at
                        else:
                            created_at = code.created_at
                    except Exception as e:
                        print(f"Ошибка при обработке даты created_at: {str(e)}")
                
                referrals_data.append({
                    'id': code.id,
                    'user_id': code.user_id,
                    'username': username,
                    'code': code.code,
                    'is_active': is_active,
                    'created_at': created_at,
                    'referral_count': referral_count,
                    'paid_count': paid_count
                })
                
            print(f"Преобразовано {len(referrals_data)} записей реферальных кодов")
        except Exception as e:
            referrals_data = []
            print(f'Ошибка при получении данных о реферальных кодах: {str(e)}')
            flash(f'Ошибка при получении данных о реферальных кодах: {str(e)}', 'error')
        
        try:
            # Получаем все записи использования рефералок
            print("Получение записей использования рефералок")
            try:
                # Пробуем сортировать по used_at в убывающем порядке
                referral_uses = db_session.query(ReferralUse).order_by(ReferralUse.used_at.desc()).all()
                print(f"Получено {len(referral_uses)} записей использования рефералок")
            except Exception as e:
                print(f"Ошибка при сортировке ReferralUse по used_at.desc(): {str(e)}")
                try:
                    # Если не получилось, используем альтернативную сортировку без desc()
                    from sqlalchemy import desc
                    referral_uses = db_session.query(ReferralUse).order_by(desc(ReferralUse.used_at)).all()
                    print(f"Получено {len(referral_uses)} записей использования через альтернативную сортировку")
                except Exception as e2:
                    print(f"Ошибка при альтернативной сортировке: {str(e2)}")
                    # Если и эта сортировка не работает, получаем данные без сортировки
                    referral_uses = db_session.query(ReferralUse).all()
                    print(f"Получено {len(referral_uses)} записей использования без сортировки")
            
            # Преобразуем в формат для шаблона
            referral_uses_data = []
            for use in referral_uses:
                try:
                    # Получаем код
                    ref_code = db_session.query(ReferralCode).filter(
                        ReferralCode.id == use.referral_code_id
                    ).first()
                    
                    # Получаем пользователя (приглашенного)
                    user = None
                    if use.user_id:
                        user = db_session.query(User).filter(
                            User.id == use.user_id
                        ).first()
                    
                    # Получаем информацию о реферере (приглашающем)
                    referrer = None
                    if hasattr(use, 'referrer_id') and use.referrer_id:
                        # Сначала ищем по ID из базы данных
                        referrer = db_session.query(User).filter(
                            User.id == use.referrer_id
                        ).first()
                        
                        # Если не нашли, ищем по Telegram ID
                        if not referrer:
                            referrer = db_session.query(User).filter(
                                User.user_id == use.referrer_id
                            ).first()
                    
                    # Получаем информацию о реферале (приглашенном) - для старых записей
                    referred = None
                    if hasattr(use, 'referred_id') and use.referred_id:
                        referred = db_session.query(User).filter(
                            User.user_id == use.referred_id
                        ).first()
                        
                        # Если нашли по старому полю, но не указан user_id, обновляем его
                        if referred and not use.user_id:
                            use.user_id = referred.id
                            db_session.commit()
                    
                    username = user.username if user else (referred.username if referred else 'Неизвестно')
                    referrer_username = referrer.username if referrer else 'Неизвестно'
                    referred_username = referred.username if referred else username
                    code_value = ref_code.code if ref_code else 'Неизвестно'
                    
                    # Определяем статус оплаты
                    payment_status = "Не оплачено"
                    payment_date = None
                    subscription_purchased = getattr(use, 'subscription_purchased', False)
                    
                    if subscription_purchased:
                        payment_status = "Оплачено"
                        payment_date = getattr(use, 'purchase_date', None)
                        
                        # Проверяем, получил ли реферер бонус
                        if getattr(use, 'reward_processed', False):
                            payment_status += " (бонус выплачен)"
                    
                    discount_applied = getattr(use, 'discount_applied', 0) if hasattr(use, 'discount_applied') else 0
                    
                    referral_uses_data.append({
                        'id': use.id,
                        'referral_code': code_value,
                        'username': username,
                        'referrer_id': getattr(use, 'referrer_id', None),
                        'referrer_username': referrer_username,
                        'referred_id': getattr(use, 'referred_id', None),
                        'referred_username': referred_username,
                        'used_at': getattr(use, 'used_at', None),
                        'status': getattr(use, 'status', 'registered'),
                        'subscription_purchased': subscription_purchased,
                        'purchase_date': payment_date,
                        'payment_status': payment_status,
                        'payment_date': payment_date,
                        'reward_processed': getattr(use, 'reward_processed', False),
                        'discount_applied': discount_applied
                    })
                except Exception as e:
                    # Пропускаем записи с ошибками
                    print(f"Ошибка при обработке записи использования реферала: {str(e)}")
                    continue
        except Exception as e:
            referral_uses_data = []
            print(f'Ошибка при получении данных об использовании реферальных кодов: {str(e)}')
            flash(f'Ошибка при получении данных об использовании реферальных кодов: {str(e)}', 'error')
        
        # Статистика реферальной системы
        try:
            total_referral_codes = len(referrals_data)
            total_referral_uses = len(referral_uses_data)
            total_paid = sum(1 for use in referral_uses_data if use.get('subscription_purchased', False))
            
            # Конверсия (для примера, можно настроить по своим критериям)
            conversion_rate = 0
            if total_referral_uses > 0:
                conversion_rate = round((total_paid / total_referral_uses) * 100, 2)
        except Exception as e:
            print(f"Ошибка при расчете статистики: {str(e)}")
            total_referral_codes = 0
            total_referral_uses = 0
            total_paid = 0
            conversion_rate = 0
        
        db_session.close()
        
        # Определяем вспомогательную функцию для форматирования дат
        def format_date(date_value, format_str='%d.%m.%Y %H:%M'):
            if date_value is None:
                return "Нет данных"
            if isinstance(date_value, str):
                return date_value
            try:
                return date_value.strftime(format_str)
            except (AttributeError, ValueError, TypeError):
                return str(date_value)
                
        return render_template('admin/referrals.html', 
                               referral_codes=referrals_data,
                               referral_uses=referral_uses_data,
                               total_referral_codes=total_referral_codes,
                               total_referral_uses=total_referral_uses,
                               total_paid=total_paid,
                               conversion_rate=conversion_rate,
                               string=str,
                               hasattr=hasattr,
                               format_date=format_date)  # Передаем функцию форматирования дат в контекст
    except Exception as e:
        flash(f'Ошибка при получении данных о реферальных кодах: {str(e)}', 'error')
        
        # Определяем вспомогательную функцию для форматирования дат
        def format_date(date_value, format_str='%d.%m.%Y %H:%M'):
            if date_value is None:
                return "Нет данных"
            if isinstance(date_value, str):
                return date_value
            try:
                return date_value.strftime(format_str)
            except (AttributeError, ValueError, TypeError):
                return str(date_value)
                
        return render_template('admin/referrals.html', 
                               referral_codes=[],
                               referral_uses=[],
                               total_referral_codes=0,
                               total_referral_uses=0,
                               total_paid=0,
                               conversion_rate=0,
                               string=str,
                               hasattr=hasattr,
                               format_date=format_date)  # Передаем функцию форматирования дат в контекст

# Маршрут для переключения активности реферального кода
@app.route('/toggle_referral_code', methods=['POST'])
@login_required
def toggle_referral_code():
    logging.info("Вызов функции toggle_referral_code")
    db_session = get_session()
    code_id = request.form.get('code_id')
    
    logging.info(f"Получен code_id: {code_id}")
    
    if not code_id:
        logging.error("Ошибка: ID реферального кода не указан")
        flash('ID реферального кода не указан', 'error')
        return redirect(url_for('referrals'))
    
    try:
        logging.info(f"Поиск кода с ID {code_id}")
        ref_code = db_session.query(ReferralCode).filter(
            ReferralCode.id == code_id
        ).first()
        
        if ref_code:
            # Переключаем статус
            logging.info(f"Код найден, текущий статус: {ref_code.is_active}")
            ref_code.is_active = not ref_code.is_active
            db_session.commit()
            
            action = "активирован" if ref_code.is_active else "деактивирован"
            logging.info(f"Код {ref_code.code} успешно {action}")
            flash(f'Реферальный код {ref_code.code} успешно {action}', 'success')
        else:
            logging.error(f"Ошибка: Реферальный код с ID {code_id} не найден")
            flash('Реферальный код не найден', 'error')
    
    except Exception as e:
        logging.error(f"Ошибка при изменении статуса реферального кода: {str(e)}")
        db_session.rollback()
        flash(f'Ошибка при изменении статуса реферального кода: {str(e)}', 'error')
    
    finally:
        db_session.close()
    
    logging.info("Завершение функции toggle_referral_code")
    return redirect(url_for('referrals'))

@app.route('/reset_referrals', methods=['POST'])
@login_required
def reset_referrals():
    db_session = get_session()
    
    try:
        db_session.query(ReferralUse).delete()
        
        db_session.query(ReferralCode).delete()
        
        db_session.commit()
        flash('Все данные реферальной системы успешно сброшены', 'success')
    
    except Exception as e:
        db_session.rollback()
        flash(f'Ошибка при сбросе данных реферальной системы: {str(e)}', 'error')
    
    finally:
        db_session.close()
    
    return redirect(url_for('referrals'))

@app.route('/admin/bloggers')
@login_required
def bloggers():
    try:
        all_bloggers = get_all_bloggers()
        total_stats = get_total_stats()
        
        # Преобразуем результаты в список словарей для безопасного изменения
        blogger_list = []
        for blogger in all_bloggers:
            # Создаем копию записи блогера в виде словаря
            blogger_dict = dict(blogger)
            
            # Обрабатываем даты
            if 'registration_date' in blogger_dict and blogger_dict['registration_date'] and isinstance(blogger_dict['registration_date'], str):
                try:
                    blogger_dict['registration_date'] = datetime.strptime(blogger_dict['registration_date'], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    pass
            elif 'join_date' in blogger_dict and blogger_dict['join_date'] and isinstance(blogger_dict['join_date'], str):
                try:
                    blogger_dict['join_date'] = datetime.strptime(blogger_dict['join_date'], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    pass
                    
            blogger_list.append(blogger_dict)
            
    except Exception as e:
        blogger_list = []
        total_stats = {'total_referrals': 0, 'total_conversions': 0, 'total_earnings': 0}
        flash(f'Ошибка при получении списка блогеров: {str(e)}', 'error')
        flash('Запустите скрипт миграции для создания таблицы блогеров', 'info')
    
    return render_template('admin/bloggers.html', bloggers=blogger_list, 
                         total_referrals=total_stats['total_referrals'],
                         total_conversions=total_stats['total_conversions'],
                         total_earnings=total_stats['total_earnings'])

@app.route('/admin/bloggers/<int:blogger_id>')
@login_required
def blogger_stats(blogger_id):
    try:
        conn = get_blogger_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM bloggers WHERE id = ?", (blogger_id,))
        blogger = cursor.fetchone()
        
        if not blogger:
            flash(f'Блогер с ID {blogger_id} не найден', 'error')
            conn.close()
            return redirect(url_for('bloggers'))
        
        # Преобразуем даты, если они представлены строками
        if 'registration_date' in blogger.keys() and blogger['registration_date'] and isinstance(blogger['registration_date'], str):
            try:
                blogger['registration_date'] = datetime.strptime(blogger['registration_date'], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                pass
        elif 'join_date' in blogger.keys() and blogger['join_date'] and isinstance(blogger['join_date'], str):
            try:
                blogger['join_date'] = datetime.strptime(blogger['join_date'], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                pass
                
        referrals = get_blogger_referrals(blogger_id, limit=100)
        
        # Преобразуем даты в переходах
        for referral in referrals:
            if 'created_at' in referral.keys() and referral['created_at'] and isinstance(referral['created_at'], str):
                try:
                    referral['created_at'] = datetime.strptime(referral['created_at'], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    pass
                    
        conn.close()
    except Exception as e:
        blogger = None
        referrals = []
        flash(f'Ошибка при получении данных о блогере: {str(e)}', 'error')
        return redirect(url_for('bloggers'))
    
    return render_template('admin/blogger_stats.html', blogger=blogger, referrals=referrals)

@app.route('/telegram-app/blogger/login')
def telegram_app_blogger_login():
    user_data = request.args.get('user_data')
    try:
        if user_data:
            user_data = json.loads(user_data)
    except Exception as e:
        app.logger.error(f"Ошибка при обработке данных пользователя: {str(e)}")
    
    return render_template('telegram_app/blogger_login.html')

@app.route('/telegram-app/blogger/dashboard')
def telegram_app_blogger_dashboard():
    return render_template('telegram_app/blogger_dashboard.html')
    
@app.route('/blogger/login')
def blogger_login():
    return render_template('blogger/login.html')

@app.route('/blogger/dashboard')
def blogger_dashboard():
    access_key = request.args.get('key')
    if not access_key:
        return redirect(url_for('blogger_login'))
    
    try:
        # Получаем данные блогера
        blogger = get_blogger_by_key(access_key)
        
        if not blogger:
            flash('Неверный ключ доступа или аккаунт деактивирован', 'error')
            return redirect(url_for('blogger_login'))
        
        # Преобразуем объект Row в словарь для безопасного изменения
        blogger_dict = dict(blogger)
        
        # Преобразуем даты, если они представлены строками
        if 'registration_date' in blogger_dict and blogger_dict['registration_date'] and isinstance(blogger_dict['registration_date'], str):
            try:
                blogger_dict['registration_date'] = datetime.strptime(blogger_dict['registration_date'], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                pass
        elif 'join_date' in blogger_dict and blogger_dict['join_date'] and isinstance(blogger_dict['join_date'], str):
            try:
                blogger_dict['join_date'] = datetime.strptime(blogger_dict['join_date'], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                pass
        
        # Формируем реферальную ссылку
        bot_username = app.config.get('TELEGRAM_BOT_USERNAME', 'willwayapp_bot')
        referral_link = f"https://t.me/{bot_username}?start=ref_{access_key}"
        
        # Получаем статистику
        stats = update_blogger_stats(blogger_dict['id'])
        
        # Получаем последние реферальные переходы
        recent_referrals = get_blogger_referrals(blogger_dict['id'], limit=10)
        
        # Преобразуем результаты в список словарей для безопасного изменения
        referrals_list = []
        for referral in recent_referrals:
            # Создаем копию записи реферала в виде словаря
            referral_dict = dict(referral)
            
            # Преобразуем даты в переходах, если они представлены строками
            if 'created_at' in referral_dict and referral_dict['created_at'] and isinstance(referral_dict['created_at'], str):
                try:
                    referral_dict['created_at'] = datetime.strptime(referral_dict['created_at'], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    pass
            
            referrals_list.append(referral_dict)
        
        return render_template('blogger/dashboard.html', 
                              blogger=blogger_dict, 
                              referral_link=referral_link,
                              total_referrals=stats['total_referrals'],
                              total_conversions=stats['total_conversions'],
                              total_earnings=stats['total_earned'],
                              recent_referrals=referrals_list)
    except Exception as e:
        flash(f'Ошибка при загрузке дашборда: {str(e)}', 'error')
        return redirect(url_for('blogger_login'))

@app.route('/api/webapp/blogger/verify', methods=['POST'])
def webapp_verify_blogger():
    data = request.get_json()
    
    if not data or 'access_key' not in data:
        return jsonify({"success": False, "error": "Не указан ключ доступа"}), 400
    
    access_key = data['access_key']
    db_session = get_session()
    blogger = db_session.query(Blogger).filter_by(access_key=access_key).first()
    db_session.close()
    
    if not blogger:
        return jsonify({"success": False, "error": "Неверный ключ доступа"}), 401
    
    return jsonify({
        "success": True,
        "blogger_id": blogger.id,
        "blogger_name": blogger.name
    })

@app.route('/api/telegram-bot/webhook', methods=['POST'])
def telegram_webhook():
    try:
        data = request.get_json()
        app.logger.info(f"Получены данные от Telegram: {json.dumps(data)}")
        
        if 'message' in data and 'text' in data['message']:
            message_text = data['message']['text']
            user_id = data['message']['from']['id']
            
            if message_text.startswith('/start ref_'):
                access_key = message_text.replace('/start ref_', '')
                
                # Получаем данные блогера
                blogger = get_blogger_by_key(access_key)
                
                if blogger:
                    # Записываем реферальный переход
                    record_referral(blogger['id'], str(user_id), f"telegram_start_{user_id}")
                    app.logger.info(f"Зарегистрирован переход по реферальной ссылке от блогера {blogger['id']}")
        
        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Ошибка при обработке вебхука: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/telegram-bot/set-webhook', methods=['GET'])
@login_required
def set_telegram_webhook():
    token = app.config.get('TELEGRAM_BOT_TOKEN')
    if not token:
        return jsonify({"success": False, "error": "Токен бота не настроен"}), 400
    
    webhook_url = request.args.get('url')
    if not webhook_url:
        return jsonify({"success": False, "error": "URL не указан"}), 400
    
    try:
        api_url = f"https://api.telegram.org/bot{token}/setWebhook"
        response = requests.post(api_url, json={"url": webhook_url})
        result = response.json()
        
        if result.get("ok"):
            return jsonify({"success": True, "result": result})
        else:
            return jsonify({"success": False, "error": result.get("description")}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/blogger/verify-key', methods=['POST'])
def api_blogger_verify_key():
    """Аутентификация блогера по ключу доступа"""
    data = request.get_json()
    
    if not data or 'access_key' not in data:
        return jsonify({"success": False, "error": "Не указан ключ доступа"}), 400
    
    access_key = data['access_key']
    db_session = get_session()
    blogger = db_session.query(Blogger).filter_by(access_key=access_key, is_active=True).first()
    db_session.close()
    
    if not blogger:
        return jsonify({"success": False, "error": "Неверный ключ доступа"}), 401
    
    return jsonify({
        "success": True,
        "blogger_id": blogger.id,
        "blogger_name": blogger.name
    })

@app.route('/admin/create-blogger', methods=['POST'])
@login_required
def create_blogger():
    """Создать нового блогера"""
    name = request.form.get('name')
    telegram_username = request.form.get('telegram_username', '')
    
    if not name:
        flash('Имя блогера обязательно', 'error')
        return redirect(url_for('bloggers'))
    
    try:
        # Проверяем таблицы блогеров
        check_blogger_table()
        
        # Подключаемся к базе данных
        conn = get_blogger_db_connection()
        cursor = conn.cursor()
        
        # Получаем схему таблицы для проверки колонок
        cursor.execute("PRAGMA table_info(bloggers)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Генерируем ключ доступа
        import secrets
        access_key = secrets.token_hex(16)
        
        # Проверяем уникальность ключа
        while True:
            cursor.execute("SELECT id FROM bloggers WHERE access_key = ?", (access_key,))
            if not cursor.fetchone():
                break
            access_key = secrets.token_hex(16)
        
        # Адаптируем SQL запрос в зависимости от структуры таблицы
        if 'email' in columns:
            email = request.form.get('email', '')
            if 'is_active' in columns:
                cursor.execute(
                    "INSERT INTO bloggers (name, telegram_id, email, access_key, registration_date, is_active) VALUES (?, ?, ?, ?, ?, ?)",
                    (name, telegram_username, email, access_key, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 1)
                )
            else:
                cursor.execute(
                    "INSERT INTO bloggers (name, telegram_id, email, access_key, registration_date) VALUES (?, ?, ?, ?, ?)",
                    (name, telegram_username, email, access_key, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
        else:
            if 'is_active' in columns:
                cursor.execute(
                    "INSERT INTO bloggers (name, telegram_id, access_key, registration_date, is_active) VALUES (?, ?, ?, ?, ?)",
                    (name, telegram_username, access_key, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 1)
                )
            else:
                cursor.execute(
                    "INSERT INTO bloggers (name, telegram_id, access_key, registration_date) VALUES (?, ?, ?, ?)",
                    (name, telegram_username, access_key, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
        
        # Получаем ID нового блогера
        blogger_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        # Формируем ссылку для блогера
        bot_username = app.config.get('TELEGRAM_BOT_USERNAME', 'willwayapp_bot')
        blogger_link = f"https://t.me/{bot_username}?start=ref_{access_key}"
        
        flash(f'Блогер {name} успешно добавлен. Ключ доступа: {access_key}', 'success')
        flash(f'Реферальная ссылка: {blogger_link}', 'info')
        
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        flash(f'Ошибка при создании блогера: {str(e)}', 'error')
    
    return redirect(url_for('bloggers'))

@app.route('/blogger/authenticate', methods=['POST'])
def blogger_authenticate():
    """Аутентификация блогера по ключу доступа"""
    access_key = request.form.get('access_key')
    
    if not access_key:
        flash('Пожалуйста, введите ключ доступа', 'error')
        return redirect(url_for('blogger_login'))
    
    # Получаем данные блогера
    try:
        blogger = get_blogger_by_key(access_key)
        
        if not blogger:
            flash('Неверный ключ доступа или аккаунт деактивирован', 'error')
            return redirect(url_for('blogger_login'))
        
        # Преобразуем объект Row в словарь для безопасной работы
        blogger_dict = dict(blogger)
        
        # Обновляем статистику блогера только если есть id
        if 'id' in blogger_dict:
            update_blogger_stats(blogger_dict['id'])
        
        # Перенаправляем на дашборд с параметром ключа
        return redirect(url_for('blogger_dashboard', key=access_key))
    
    except Exception as e:
        flash(f'Ошибка при проверке ключа: {str(e)}', 'error')
        return redirect(url_for('blogger_login'))

@app.route('/blogger/logout')
def blogger_logout():
    """Выход из личного кабинета блогера"""
    return redirect(url_for('blogger_login'))

@app.template_filter('from_json')
def from_json(value):
    if not value:
        return {}
    try:
        return json.loads(value)
    except:
        return {}

@app.route('/api/user/<int:user_id>/subscription-info', methods=['GET'])
@login_required
def get_user_subscription_info(user_id):
    """
    Получить информацию о подписке пользователя, включая данные по отмене
    """
    db_session = get_session()
    user = db_session.query(User).filter(User.id == user_id).first()
    
    if not user:
        db_session.close()
        return jsonify({'error': 'Пользователь не найден'}), 404
    
    # Базовая информация о подписке
    subscription_info = {
        'is_subscribed': user.is_subscribed,
        'subscription_type': user.subscription_type,
        'subscription_expires': user.subscription_expires.isoformat() if user.subscription_expires else None
    }
    
    # Информация об отмене подписки
    cancellation_info = {
        'cancellation_date': user.cancellation_date.isoformat() if hasattr(user, 'cancellation_date') and user.cancellation_date else None,
        'cancellation_reason_1': user.cancellation_reason_1 if hasattr(user, 'cancellation_reason_1') else None,
        'cancellation_reason_2': user.cancellation_reason_2 if hasattr(user, 'cancellation_reason_2') else None,
        'cancellation_additional_comment': user.cancellation_additional_comment if hasattr(user, 'cancellation_additional_comment') else None
    }
    
    # Проверяем метаданные на наличие информации об отмене
    metadata = {}
    if hasattr(user, 'metadata') and user.metadata:
        try:
            import json
            metadata = json.loads(user.metadata) if isinstance(user.metadata, str) else user.metadata
            if 'is_cancellation_requested' in metadata:
                cancellation_info['is_cancellation_requested'] = metadata['is_cancellation_requested']
        except:
            app.logger.warning(f"Не удалось разобрать метаданные пользователя {user_id}")
    
    db_session.close()
    
    return jsonify({
        'success': True,
        'subscription_info': subscription_info,
        'cancellation_info': cancellation_info,
        'metadata': metadata
    })

@app.route('/dashboard')
def dashboard():
    """Редирект с /dashboard на /admin/dashboard для совместимости"""
    return redirect(url_for('admin_dashboard'))

@app.route('/api/blogger/toggle-status', methods=['POST'])
@login_required
def toggle_blogger_status_route():
    """Изменить статус блогера (активный/неактивный)"""
    data = request.get_json()
    
    if not data or 'blogger_id' not in data or 'activate' not in data:
        return jsonify({"success": False, "error": "Неверные параметры запроса"}), 400
    
    blogger_id = data['blogger_id']
    activate = data['activate']
    
    try:
        # Подключаемся к базе willway_bloggers.db
        conn = get_blogger_db_connection()
        cursor = conn.cursor()
        
        # Проверяем существование блогера
        cursor.execute("SELECT id FROM bloggers WHERE id = ?", (blogger_id,))
        blogger = cursor.fetchone()
        
        if not blogger:
            conn.close()
            return jsonify({"success": False, "error": "Блогер не найден"}), 404
        
        # Проверяем структуру таблицы
        cursor.execute("PRAGMA table_info(bloggers)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Изменяем статус блогера в зависимости от структуры таблицы
        if 'is_active' in columns:
            cursor.execute("UPDATE bloggers SET is_active = ? WHERE id = ?", (1 if activate else 0, blogger_id))
            conn.commit()
        else:
            # Если колонки is_active нет, то добавляем её
            try:
                cursor.execute("ALTER TABLE bloggers ADD COLUMN is_active INTEGER DEFAULT 1")
                cursor.execute("UPDATE bloggers SET is_active = ? WHERE id = ?", (1 if activate else 0, blogger_id))
                conn.commit()
            except Exception as e:
                # В случае ошибки при добавлении колонки, используем функцию из blogger_utils если она доступна
                try:
                    from web_admin.blogger_utils import toggle_blogger_status
                    toggle_blogger_status(blogger_id, activate)
                except ImportError:
                    conn.close()
                    return jsonify({"success": False, "error": f"Невозможно изменить статус блогера: {str(e)}"}), 500
        
        conn.close()
        return jsonify({"success": True})
        
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/stats')
@login_required
def admin_stats():
    """Получение статистики для админ-панели"""
    try:
        stats = get_total_stats()
        return jsonify({
            "success": True,
            "total_bloggers": len(get_all_bloggers()),
            "total_referrals": stats['total_referrals'],
            "total_earnings": stats['total_earnings']
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/blogger/stats')
def blogger_stats_api():
    """API для получения статистики блогера"""
    access_key = request.args.get('key')
    
    if not access_key:
        return jsonify({"success": False, "error": "Не указан ключ доступа"}), 400
    
    try:
        # Получаем данные блогера
        blogger = get_blogger_by_key(access_key)
        
        if not blogger:
            return jsonify({"success": False, "error": "Блогер не найден"}), 404
        
        # Обновляем статистику
        stats = update_blogger_stats(blogger['id'])
        
        return jsonify({
            "success": True, 
            "stats": stats
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Создаем таблицы, если их нет
    app.run(debug=True, host="0.0.0.0", port=5001) 