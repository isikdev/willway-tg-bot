from flask import Flask, jsonify, send_from_directory
import os
import logging
from database.db import init_flask_db
from flask_cors import CORS  # Добавляем импорт для CORS

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def create_app():
    """
    Создает и настраивает Flask приложение
    
    Returns:
        Flask: Настроенное Flask приложение
    """
    # Создаем экземпляр Flask
    app = Flask(__name__)
    
    # Разрешаем CORS для всех маршрутов и для всех доменов
    CORS(app, resources={r"/*": {"origins": "*"}})
    logger.info("Настроен CORS для всех доменов")
    
    # Убираем SERVER_NAME, так как он вызывает проблемы при использовании Nginx
    # app.config['SERVER_NAME'] = os.getenv('SERVER_NAME', 'api-willway.ru')
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    
    # Добавляем настройки базы данных
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Добавляем контекстный процессор для передачи bot_username во все шаблоны
    @app.context_processor
    def inject_bot_username():
        return {'bot_username': os.getenv('TELEGRAM_BOT_USERNAME', 'willwayapp_bot')}
    
    # Инициализация базы данных SQLAlchemy
    init_flask_db(app)
    logger.info("Инициализирована база данных Flask-SQLAlchemy")
    
    # Регистрируем маршруты для платежей
    from web.payment_routes import payment_bp
    app.register_blueprint(payment_bp)
    logger.info("Зарегистрированы маршруты для платежей")
    
    # Маршрут для отдачи JS-скрипта для страницы тарифов
    @app.route('/static/js/tilda-tracker.js')
    def serve_tilda_tracker():
        response = send_from_directory(os.path.join(app.root_path, 'static/js'), 'tilda-tracker.js')
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Content-Type'] = 'application/javascript'
        return response
    
    # Маршрут для отдачи JS-скрипта для страницы успешной оплаты
    @app.route('/static/js/tilda-success.js')
    def serve_tilda_success():
        response = send_from_directory(os.path.join(app.root_path, 'static/js'), 'tilda-success.js')
        # Добавляем заголовок с Content-Type для JavaScript
        response.headers['Content-Type'] = 'application/javascript'
        response.headers['Access-Control-Allow-Origin'] = '*'
        # Добавляем переменную BOT_USERNAME в начало JS файла
        bot_username = os.getenv('TELEGRAM_BOT_USERNAME', 'willwayapp_bot')
        js_script = f"window.BOT_USERNAME = '{bot_username}';\n" + response.get_data(as_text=True)
        response.set_data(js_script)
        return response
    
    # Маршрут для проверки работы сервера
    @app.route('/health')
    def health_check():
        return jsonify({"status": "ok", "message": "Server is running"})
    
    # Обработчик ошибок
    @app.errorhandler(404)
    def page_not_found(e):
        return jsonify({"error": "Not found", "status": 404}), 404
    
    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error", "status": 500}), 500
    
    logger.info("Flask-приложение успешно создано и настроено")
    return app
