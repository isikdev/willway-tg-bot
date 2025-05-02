from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy() 

def init_flask_db(app):
    db.init_app(app)
    app.app_context().push()
    return db 