from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Blueprint
from functools import wraps
import os
from datetime import datetime, timedelta
import calendar
from sqlalchemy import func, extract
from database.models import get_session, User, AdminUser, ReferralCode, ReferralUse, Blogger, BloggerReferral, BloggerPayment, generate_access_key, Payment
from dotenv import load_dotenv
import json
import requests
from werkzeug.utils import secure_filename
from database.db import db
from flask_migrate import Migrate
from web_admin.api_routes import api_bp

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

# Конфигурация базы данных
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL", "sqlite:///health_bot.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация базы данных
db.init_app(app)
migrate = Migrate(app, db)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация для Telegram бота
app.config['TELEGRAM_BOT_TOKEN'] = os.getenv("TELEGRAM_BOT_TOKEN", "")
app.config['TELEGRAM_BOT_USERNAME'] = os.getenv("TELEGRAM_BOT_USERNAME", "willway_super_bot")
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
            return redirect(url_for('dashboard'))
        else:
            flash('Неверное имя пользователя или пароль', 'error')
    
    return render_template('admin/login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# Маршрут для главной страницы админки (аналитика)
@app.route('/')
@login_required
def dashboard():
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
    # Предполагаем, что стоимость подписки 990 рублей
    monthly_revenue = subscriptions_this_month * 990
    
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
@app.route('/api/user/<int:user_id>')
@login_required
def get_user(user_id):
    db_session = get_session()
    user = db_session.query(User).filter(User.id == user_id).first()
    
    if not user:
        db_session.close()
        return jsonify({'error': 'Пользователь не найден'}), 404
    
    user_data = {
        'id': user.id,
        'user_id': user.user_id,
        'username': user.username,
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
        'registration_date': user.registration_date.strftime('%d.%m.%Y') if user.registration_date else None,
        'is_subscribed': user.is_subscribed,
        'subscription_type': user.subscription_type,
        'subscription_expires': user.subscription_expires.strftime('%d.%m.%Y') if user.subscription_expires else None
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
    db_session = get_session()
    
    try:
        # Получаем все реферальные коды
        referral_codes = db_session.query(ReferralCode).all()
        
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
                
            referrals_data.append({
                'id': code.id,
                'user_id': code.user_id,
                'username': username,
                'code': code.code,
                'is_active': is_active,
                'created_at': getattr(code, 'created_at', None),
                'referral_count': referral_count,
                'paid_count': paid_count
            })
    except Exception as e:
        referrals_data = []
        flash(f'Ошибка при получении данных о реферальных кодах: {str(e)}', 'error')
    
    try:
        # Получаем все записи использования рефералок
        try:
            # Пробуем сортировать по used_at в убывающем порядке
            referral_uses = db_session.query(ReferralUse).order_by(ReferralUse.used_at.desc()).all()
        except Exception as e:
            print(f"Ошибка при сортировке ReferralUse по used_at.desc(): {str(e)}")
            try:
                # Если не получилось, используем альтернативную сортировку без desc()
                from sqlalchemy import desc
                referral_uses = db_session.query(ReferralUse).order_by(desc(ReferralUse.used_at)).all()
            except Exception as e2:
                print(f"Ошибка при альтернативной сортировке: {str(e2)}")
                # Если и эта сортировка не работает, получаем данные без сортировки
                referral_uses = db_session.query(ReferralUse).all()
        
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
    
    return render_template('admin/referrals.html', 
                           referral_codes=referrals_data,
                           referral_uses=referral_uses_data,
                           total_referral_codes=total_referral_codes,
                           total_referral_uses=total_referral_uses,
                           total_paid=total_paid,
                           conversion_rate=conversion_rate)

# Маршрут для переключения активности реферального кода
@app.route('/toggle-referral-code', methods=['POST'])
@login_required
def toggle_referral_code():
    db_session = get_session()
    code_id = request.form.get('code_id')
    
    if not code_id:
        flash('ID реферального кода не указан', 'error')
        return redirect(url_for('referrals'))
    
    try:
        ref_code = db_session.query(ReferralCode).filter(
            ReferralCode.id == code_id
        ).first()
        
        if ref_code:
            # Переключаем статус
            ref_code.is_active = not ref_code.is_active
            db_session.commit()
            
            action = "активирован" if ref_code.is_active else "деактивирован"
            flash(f'Реферальный код {ref_code.code} успешно {action}', 'success')
        else:
            flash('Реферальный код не найден', 'error')
    
    except Exception as e:
        db_session.rollback()
        flash(f'Ошибка при изменении статуса реферального кода: {str(e)}', 'error')
    
    finally:
        db_session.close()
    
    return redirect(url_for('referrals'))

# Маршрут для сброса данных реферальной системы
@app.route('/reset-referrals', methods=['POST'])
@login_required
def reset_referrals():
    db_session = get_session()
    
    try:
        # Удаляем все записи использования рефералок
        db_session.query(ReferralUse).delete()
        
        # Удаляем все реферальные коды
        db_session.query(ReferralCode).delete()
        
        db_session.commit()
        flash('Все данные реферальной системы успешно сброшены', 'success')
    
    except Exception as e:
        db_session.rollback()
        flash(f'Ошибка при сбросе данных реферальной системы: {str(e)}', 'error')
    
    finally:
        db_session.close()
    
    return redirect(url_for('referrals'))

# Маршрут для страницы блогеров
@app.route('/admin/bloggers')
@login_required
def bloggers():
    db_session = get_session()
    
    try:
        # Пробуем получить всех блогеров
        all_bloggers = db_session.query(Blogger).all()
    except Exception as e:
        # В случае ошибки (например, таблица не существует)
        all_bloggers = []
        flash(f'Ошибка при получении списка блогеров: {str(e)}', 'error')
        flash('Запустите скрипт миграции для создания таблицы блогеров', 'info')
    
    db_session.close()
    return render_template('admin/bloggers.html', bloggers=all_bloggers)

@app.route('/admin/bloggers/<int:blogger_id>')
@login_required
def blogger_stats(blogger_id):
    db_session = get_session()
    
    try:
        blogger = db_session.query(Blogger).filter(Blogger.id == blogger_id).first()
        if not blogger:
            flash(f'Блогер с ID {blogger_id} не найден', 'error')
            db_session.close()
            return redirect(url_for('bloggers'))
            
        referrals = db_session.query(BloggerReferral).filter(
            BloggerReferral.blogger_id == blogger_id
        ).order_by(BloggerReferral.created_at.desc()).all()
    except Exception as e:
        blogger = None
        referrals = []
        flash(f'Ошибка при получении данных о блогере: {str(e)}', 'error')
        db_session.close()
        return redirect(url_for('bloggers'))
    
    db_session.close()
    return render_template('admin/blogger_stats.html', blogger=blogger, referrals=referrals)

# Регистрация API Blueprint
app.register_blueprint(api_bp, url_prefix='/api')

# Маршруты для мини-приложения Telegram
@app.route('/telegram-app/blogger/login')
def telegram_app_blogger_login():
    # Получаем параметры от Telegram WebApp
    user_data = request.args.get('user_data')
    try:
        if user_data:
            user_data = json.loads(user_data)
            # Логика проверки авторизации блогера может быть добавлена здесь
    except Exception as e:
        app.logger.error(f"Ошибка при обработке данных пользователя: {str(e)}")
    
    return render_template('admin/telegram_app/login.html')

@app.route('/telegram-app/blogger/dashboard')
def telegram_app_blogger_dashboard():
    # Получаем параметры от Telegram WebApp
    blogger_id = request.args.get('id')
    access_key = request.args.get('key')
    
    # Проверяем ключ доступа
    db_session = get_session()
    blogger = None
    if blogger_id and access_key:
        blogger = db_session.query(Blogger).filter_by(id=blogger_id, access_key=access_key).first()
    
    if not blogger:
        db_session.close()
        return redirect(url_for('telegram_app_blogger_login'))
    
    # Получаем статистику
    total_referrals = db_session.query(BloggerReferral).filter_by(blogger_id=blogger.id).count()
    total_conversions = db_session.query(BloggerReferral).filter_by(blogger_id=blogger.id, converted=True).count()
    total_earnings = db_session.query(func.sum(BloggerReferral.commission_amount))\
        .filter_by(blogger_id=blogger.id, converted=True)\
        .scalar() or 0
    
    db_session.close()
    
    # Формируем реферальную ссылку
    bot_username = app.config.get('TELEGRAM_BOT_USERNAME', 'WILLWAY_ReferalBot')
    referral_link = f"https://t.me/{bot_username}?start=ref_{blogger.access_key}"
    
    return render_template('admin/telegram_app/dashboard.html', 
                          blogger=blogger, 
                          total_referrals=total_referrals,
                          total_conversions=total_conversions,
                          total_earnings=total_earnings,
                          referral_link=referral_link)

# Добавляем API для Mini Web App
@app.route('/api/webapp/blogger/verify', methods=['POST'])
def webapp_verify_blogger():
    """Проверка данных блогера для Mini Web App"""
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

@app.route('/api/webapp/blogger/stats', methods=['GET'])
def webapp_get_blogger_stats():
    """Получение статистики блогера для Mini Web App"""
    blogger_id = request.args.get('id')
    access_key = request.args.get('key')
    
    if not blogger_id or not access_key:
        return jsonify({"success": False, "error": "Не указаны параметры доступа"}), 400
    
    # Проверка ключа доступа
    db_session = get_session()
    blogger = db_session.query(Blogger).filter_by(id=blogger_id, access_key=access_key).first()
    
    if not blogger:
        db_session.close()
        return jsonify({"success": False, "error": "Нет доступа"}), 401
    
    # Получаем общее количество переходов
    total_referrals = db_session.query(BloggerReferral).filter_by(blogger_id=blogger.id).count()
    
    # Получаем общее количество конверсий
    total_conversions = db_session.query(BloggerReferral).filter_by(blogger_id=blogger.id, converted=True).count()
    
    # Получаем общую сумму заработка
    total_earnings = db_session.query(func.sum(BloggerReferral.commission_amount))\
        .filter_by(blogger_id=blogger.id, converted=True)\
        .scalar() or 0
    
    # Формируем реферальную ссылку
    bot_username = app.config.get('TELEGRAM_BOT_USERNAME', 'WILLWAY_ReferalBot')
    referral_link = f"https://t.me/{bot_username}?start=ref_{blogger.access_key}"
    
    db_session.close()
    
    return jsonify({
        "success": True,
        "blogger_id": blogger.id,
        "blogger_name": blogger.name,
        "created_at": blogger.created_at.strftime("%Y-%m-%d"),
        "total_referrals": total_referrals,
        "total_conversions": total_conversions,
        "total_earnings": total_earnings,
        "referral_link": referral_link
    })

@app.route('/api/telegram-bot/webhook', methods=['POST'])
def telegram_webhook():
    """Обработчик вебхуков от Telegram бота"""
    try:
        data = request.get_json()
        app.logger.info(f"Получены данные от Telegram: {json.dumps(data)}")
        
        # Обработка команды start с реферальным кодом
        if 'message' in data and 'text' in data['message']:
            message_text = data['message']['text']
            user_id = data['message']['from']['id']
            
            # Проверяем начало разговора с ботом со ссылкой реферала
            if message_text.startswith('/start ref_'):
                access_key = message_text.replace('/start ref_', '')
                
                # Проверяем существование блогера с таким ключом
                db_session = get_session()
                blogger = db_session.query(Blogger).filter_by(access_key=access_key).first()
                
                if blogger:
                    # Создаем запись о переходе
                    new_referral = BloggerReferral(
                        blogger_id=blogger.id,
                        source=f"telegram_start_{user_id}"
                    )
                    db_session.add(new_referral)
                    db_session.commit()
                    app.logger.info(f"Зарегистрирован переход по реферальной ссылке от блогера {blogger.id}")
                
                db_session.close()
        
        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Ошибка при обработке вебхука: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# Функция для установки вебхука
@app.route('/api/telegram-bot/set-webhook', methods=['GET'])
@login_required
def set_telegram_webhook():
    """Установка вебхука для Telegram бота"""
    token = app.config.get('TELEGRAM_BOT_TOKEN')
    if not token:
        return jsonify({"success": False, "error": "Токен бота не настроен"}), 400
    
    webhook_url = request.args.get('url')
    if not webhook_url:
        return jsonify({"success": False, "error": "URL не указан"}), 400
    
    try:
        # Формируем URL для установки вебхука
        api_url = f"https://api.telegram.org/bot{token}/setWebhook"
        response = requests.post(api_url, json={"url": webhook_url})
        result = response.json()
        
        if result.get("ok"):
            return jsonify({"success": True, "result": result})
        else:
            return jsonify({"success": False, "error": result.get("description")}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Создаем таблицы, если их нет
    app.run(debug=True, host='0.0.0.0', port=5000) 