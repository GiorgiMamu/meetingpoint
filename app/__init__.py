import logging
import os
from logging.handlers import RotatingFileHandler
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf import CSRFProtect
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_socketio import SocketIO
from config import config

db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()
csrf = CSRFProtect()
mail = Mail()
migrate = Migrate()
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "600 per hour"])
socketio = SocketIO()

def create_app(config_name='default'):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config[config_name])

    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)
    if not app.config.get('TESTING'):
        migrate.init_app(app, db)
    limiter.init_app(app)
    socketio.init_app(app, cors_allowed_origins='*')

    login_manager.login_view = 'main.login'
    login_manager.login_message_category = 'info'

    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler(
        app.config['LOG_FILE'], maxBytes=10240, backupCount=5, delay=True
    )
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    )
    file_handler.setFormatter(formatter)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('MeetingPoint startup')

    from app import models

    @app.context_processor
    def inject_category_labels():
        category_labels = {
            'social': 'Social',
            'sports': 'Sports',
            'arts and culture': 'Arts & Culture',
            'music': 'Music',
            'food and drinks': 'Food & Drinks',
            'outdoors': 'Outdoors',
            'games': 'Games',
            'education': 'Education',
            'technology': 'Technology',
            'wellness and health': 'Wellness & Health',
            'travel': 'Travel',
            'other': 'Other'
        }
        return dict(category_labels=category_labels)

    from app.routes import main
    app.register_blueprint(main)

    from app.socket_events import register_socket_events
    register_socket_events(socketio)

    @app.before_request
    def make_session_permanent():
        from flask import session
        session.permanent = True

    if not app.config.get('TESTING'):
        from app.scheduler import start_scheduler
        start_scheduler(app)

    return app