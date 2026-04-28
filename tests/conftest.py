import pytest
from app import create_app, db

@pytest.fixture
def app():
    app = create_app('development')
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False

    app.config['MAIL_SUPPRESS_SEND'] = True

    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()