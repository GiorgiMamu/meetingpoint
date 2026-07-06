import os
from dotenv import load_dotenv
load_dotenv()

def get_database_url():
    url = os.environ.get('DATABASE_URL') or 'sqlite:///meetingpoint.db'
    # Render uses postgres:// but SQLAlchemy requires postgresql://
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    return url


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-change-in-production'
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024

    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_USERNAME') or os.environ.get('MAIL_DEFAULT_SENDER')

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_DURATION = 2592000

    from datetime import timedelta
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    LOG_FILE = 'logs/meetingpoint.log'


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    RATELIMIT_STORAGE_URI = 'memory://'


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    RATELIMIT_STORAGE_URI = 'memory://'


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
    'testing': TestingConfig,
}