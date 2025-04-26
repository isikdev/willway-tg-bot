from flask import Flask, jsonify, send_from_directory
import os
import logging

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
    
    # Настройка для работы с доменом api-willway.ru
    app.config['SERVER_NAME'] = os.getenv('SERVER_NAME', 'api-willway.ru')
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    
    # Регистрируем маршруты для платежей
    from web.payment_routes import payment_bp
    app.register_blueprint(payment_bp)
    logger.info("Зарегистрированы маршруты для платежей")
    
    # Маршрут для отдачи JS-скрипта для страницы тарифов
    @app.route('/static/js/tilda-tracker.js')
    def serve_tilda_tracker():
        return send_from_directory(os.path.join(app.root_path, 'static/js'), 'tilda-tracker.js')
    
    # Маршрут для отдачи JS-скрипта для страницы успешной оплаты
    @app.route('/static/js/tilda-success.js')
    def serve_tilda_success():
        return send_from_directory(os.path.join(app.root_path, 'static/js'), 'tilda-success.js')
    
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
