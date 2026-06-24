import pytest

from app import create_app, db as _db


@pytest.fixture(scope='function')
def app():
    app = create_app('testing')
    app.config['RATELIMIT_ENABLED'] = False

    with app.app_context():
        _db.drop_all()       # clean up any leftovers from a previously failed test

        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()
        _db.engine.dispose()


@pytest.fixture(scope='function')
def client(app):
    return app.test_client()
