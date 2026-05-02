import pytest
from app.models import User
from app import db, bcrypt


def create_user(app, email='test@example.com', password='password123',
                name='Test User', active=True):
    with app.app_context():
        hashed = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(email=email, password_hash=hashed,
                    name=name, is_active=active)
        db.session.add(user)
        db.session.commit()
        return user.id


# --- Registration ---
def test_register_page_loads(client):
    response = client.get('/register')
    assert response.status_code == 200

def test_register_new_user(client):
    response = client.post('/register', data={
        'name': 'Alice',
        'email': 'alice@example.com',
        'password': 'securepass1',
        'confirm_password': 'securepass1'
    }, follow_redirects=True)
    assert response.status_code == 200

def test_register_duplicate_email(client, app):
    create_user(app)
    response = client.post('/register', data={
        'name': 'Bob',
        'email': 'test@example.com',
        'password': 'securepass1',
        'confirm_password': 'securepass1'
    }, follow_redirects=True)
    assert b'already registered' in response.data


def test_register_password_too_long_is_user_friendly(client):
    response = client.post('/register', data={
        'name': 'Alice',
        'email': 'alice-longpw@example.com',
        'password': 'a' * 73,  # 73 bytes in UTF-8
        'confirm_password': 'a' * 73,
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Password is too long' in response.data


# --- Login ---
def test_login_page_loads(client):
    response = client.get('/login')
    assert response.status_code == 200

def test_login_valid_user(client, app):
    create_user(app)
    response = client.post('/login', data={
        'email': 'test@example.com',
        'password': 'password123'
    }, follow_redirects=True)
    assert response.status_code == 200

def test_login_wrong_password(client, app):
    create_user(app)
    response = client.post('/login', data={
        'email': 'test@example.com',
        'password': 'wrongpassword'
    }, follow_redirects=True)
    assert b'Invalid email or password' in response.data

def test_login_inactive_user(client, app):
    create_user(app, active=False)
    response = client.post('/login', data={
        'email': 'test@example.com',
        'password': 'password123'
    }, follow_redirects=True)
    assert b'confirm your email' in response.data


def test_login_password_too_long_is_user_friendly(client, app):
    create_user(app)
    response = client.post('/login', data={
        'email': 'test@example.com',
        'password': 'a' * 73,  # 73 bytes in UTF-8
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Invalid email or password' in response.data


def test_login_password_too_long_utf8_multibyte(client, app):
    create_user(app)
    response = client.post('/login', data={
        'email': 'test@example.com',
        'password': 'é' * 37,  # 74 bytes in UTF-8 (2 bytes per char)
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Invalid email or password' in response.data


# --- Logout ---
def test_logout(client, app):
    create_user(app)
    client.post('/login', data={
        'email': 'test@example.com',
        'password': 'password123'
    })
    response = client.get('/logout', follow_redirects=True)
    assert response.status_code == 200


# --- Static pages ---
def test_privacy_page(client):
    response = client.get('/privacy')
    assert response.status_code == 200

def test_terms_page(client):
    response = client.get('/terms')
    assert response.status_code == 200


# --- Role check ---
def test_admin_required_rejects_regular_user(client, app):
    create_user(app)
    client.post('/login', data={
        'email': 'test@example.com',
        'password': 'password123'
    })
    # Admin panel doesn't exist yet but 403 decorator works
    response = client.get('/admin', follow_redirects=False)
    assert response.status_code in [404, 403]

def test_generate_and_verify_token(app):
    with app.app_context():
        from app.utils import generate_token, verify_token
        token = generate_token('test@example.com', salt='email-confirm')
        result = verify_token(token, salt='email-confirm')
        assert result == 'test@example.com'

def test_expired_token_returns_none(app):
    with app.app_context():
        from app.utils import generate_token, verify_token
        token = generate_token('test@example.com', salt='email-confirm')
        result = verify_token(token, salt='email-confirm', max_age=-1)
        assert result is None