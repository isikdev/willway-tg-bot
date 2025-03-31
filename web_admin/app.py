from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps
import os
from datetime import datetime, timedelta
import calendar
from sqlalchemy import func, extract
from database.models import get_session, User, AdminUser
from dotenv import load_dotenv
import json
import requests
from werkzeug.utils import secure_filename
# Импортируем blueprint для маршрутов оплаты
try:
    from web.payment_routes import payment_routes
except ImportError:
    # Если не удалось импортировать, создаем пустой класс
    from flask import Blueprint
    payment_routes = Blueprint('payment_routes', __name__)
    print("ВНИМАНИЕ: Не удалось импортировать payment_routes. Функционал оплаты будет ограничен.")

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'img')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

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
    user = db_session.query(User).filter(User.id == user_id).first()
    
    if not user:
        db_session.close()
        return jsonify({'error': 'Пользователь не найден'}), 404
    
    # Удаляем пользователя
    db_session.delete(user)
    db_session.commit()
    db_session.close()
    
    return jsonify({'success': True, 'message': 'Пользователь успешно удален'})

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
        "description_pic_url": "",
        "botpic_url": "",
        "privacy_mode": False,
        "trainer_username": "",
        "manager_username": "",
        "channel_url": "https://t.me/willway_channel",
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
    
    # Получаем список обычных пользователей для добавления в админы (исключаем уже существующих админов)
    admin_user_ids = [admin.user_id for admin in admins]
    non_admin_users = db_session.query(User).filter(~User.user_id.in_(admin_user_ids)).limit(10).all()
    
    if request.method == 'POST':
        action = request.form.get('action', '')
        
        # Обработка действий с администраторами
        if action == 'add_admin':
            user_id = request.form.get('user_id')
            username = request.form.get('username', '')
            
            if not user_id:
                flash('ID пользователя не указан', 'error')
            else:
                try:
                    db_session = get_session()
                    # Проверяем, существует ли пользователь в базе
                    user = db_session.query(User).filter(User.user_id == user_id).first()
                    
                    # Проверяем, не является ли пользователь уже админом
                    existing_admin = db_session.query(AdminUser).filter(AdminUser.user_id == user_id).first()
                    
                    if existing_admin:
                        flash(f'Пользователь с ID {user_id} уже является администратором', 'warning')
                    else:
                        # Если пользователь существует, устанавливаем его имя из базы
                        if user:
                            username = user.username or username
                        
                        # Добавляем нового админа
                        new_admin = AdminUser(user_id=user_id, username=username)
                        db_session.add(new_admin)
                        db_session.commit()
                        flash(f'Администратор с ID {user_id} успешно добавлен', 'success')
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
                        flash(f'Администратор с ID {admin.user_id} успешно удален', 'success')
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
                    "description_pic_url": current_config.get("description_pic_url", ""),
                    "botpic_url": current_config.get("botpic_url", ""),
                    "trainer_username": request.form.get('trainer_username', default_config.get("trainer_username", "")),
                    "manager_username": request.form.get('manager_username', default_config.get("manager_username", "")),
                    "channel_url": request.form.get('channel_url', default_config.get("channel_url", "https://t.me/willway_channel")),
                    "commands": current_config.get("commands", default_config["commands"])
                }
                
                # Обрабатываем загрузку изображения описания
                if 'description_pic' in request.files and request.files['description_pic'].filename:
                    file = request.files['description_pic']
                    if allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        # Добавляем временную метку к имени файла для уникальности
                        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                        new_filename = f"{timestamp}_{filename}"
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
                        file.save(filepath)
                        # Обновляем URL в конфигурации с относительным путем от корня проекта
                        img_rel_path = os.path.join("web_admin", "static", "img", new_filename).replace("\\", "/")
                        updated_config["description_pic_url"] = f"/{img_rel_path}"
                        flash(f'Изображение описания успешно загружено: {img_rel_path}', 'success')
                
                # Обрабатываем загрузку аватара бота
                if 'botpic' in request.files and request.files['botpic'].filename:
                    file = request.files['botpic']
                    if allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        # Добавляем временную метку к имени файла для уникальности
                        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                        new_filename = f"{timestamp}_{filename}"
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
                        file.save(filepath)
                        # Обновляем URL в конфигурации с относительным путем от корня проекта
                        img_rel_path = os.path.join("web_admin", "static", "img", new_filename).replace("\\", "/")
                        updated_config["botpic_url"] = f"/{img_rel_path}"
                        flash(f'Аватар бота успешно загружен: {img_rel_path}', 'success')
                
                # Проверяем, нужно ли удалить изображения
                if 'remove_description_pic' in request.form:
                    updated_config["description_pic_url"] = ""
                    flash('Изображение описания удалено', 'success')
                
                if 'remove_botpic' in request.form:
                    updated_config["botpic_url"] = ""
                    flash('Аватар бота удален', 'success')
                
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

# Регистрация blueprint для маршрутов оплаты
app.register_blueprint(payment_routes)

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000) 