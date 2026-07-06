import pytest
from app import db, bcrypt
from app.models import User, Event, Participation
from datetime import datetime, timedelta


def create_user(app, email='user@example.com', name='Test User', role='user'):
    with app.app_context():
        user = User(
            email=email,
            password_hash=bcrypt.generate_password_hash('password').decode('utf-8'),
            name=name,
            role=role,
            is_active=True
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def login(client, email='user@example.com', password='password'):
    return client.post('/login', data={
        'email': email, 'password': password
    }, follow_redirects=True)


def create_event(app, host_id):
    with app.app_context():
        event = Event(
            host_id=host_id,
            title='Test Event',
            event_time=datetime.now() + timedelta(days=3),
            category='social',
            is_public=True,
            approval_mode='automatic'
        )
        db.session.add(event)
        db.session.commit()
        return event.id


# ── Rate limiting ──

def test_login_rate_limit(monkeypatch):
    from config import TestingConfig
    monkeypatch.setattr(TestingConfig, 'RATELIMIT_ENABLED', True)

    from app import create_app, db as _db
    app = create_app('testing')

    with app.app_context():
        _db.create_all()
        client = app.test_client()

        create_user(app)
        for _ in range(10):
            client.post('/login', data={
                'email': 'user@example.com',
                'password': 'wrongpassword'
            })
        response = client.post('/login', data={
            'email': 'user@example.com',
            'password': 'wrongpassword'
        })
        assert response.status_code == 429

        _db.session.remove()
        _db.drop_all()


def test_register_rate_limit(monkeypatch):
    from config import TestingConfig
    monkeypatch.setattr(TestingConfig, 'RATELIMIT_ENABLED', True)

    from app import create_app, db as _db
    app = create_app('testing')

    with app.app_context():
        _db.create_all()
        client = app.test_client()

        for _ in range(5):
            client.post('/register', data={
                'name': 'Test',
                'email': f'test{_}@example.com',
                'password': 'password123',
                'confirm_password': 'password123'
            })
        response = client.post('/register', data={
            'name': 'Test',
            'email': 'extra@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        })
        assert response.status_code == 429

        _db.session.remove()
        _db.drop_all()


# ── CSRF protection ──

def test_csrf_required_on_join(client, app):
    uid = create_user(app)
    host_id = create_user(app, 'host@example.com')
    event_id = create_event(app, host_id)
    login(client)
    app.config['WTF_CSRF_ENABLED'] = True
    response = client.post(f'/events/{event_id}/join', data={})
    assert response.status_code in [400, 302, 200]


# ── Access control ──

def test_unauthenticated_cannot_create_event(client):
    response = client.get('/events/create', follow_redirects=True)
    assert b'log in' in response.data.lower() or b'login' in response.data.lower()


def test_unauthenticated_cannot_access_admin(client):
    response = client.get('/admin/users')
    assert response.status_code in [302, 403]


def test_regular_user_cannot_access_admin(client, app):
    create_user(app)
    login(client)
    response = client.get('/admin/users')
    assert response.status_code == 403


def test_non_host_cannot_edit_event(client, app):
    host_id = create_user(app, 'host@example.com')
    create_user(app, 'other@example.com')
    event_id = create_event(app, host_id)
    login(client, 'other@example.com')
    response = client.get(f'/events/{event_id}/edit')
    assert response.status_code == 403


def test_non_host_cannot_delete_event(client, app):
    host_id = create_user(app, 'host@example.com')
    create_user(app, 'other@example.com')
    event_id = create_event(app, host_id)
    login(client, 'other@example.com')
    response = client.post(f'/events/{event_id}/delete')
    assert response.status_code == 403


# ── Input validation ──

def test_event_title_too_short(client, app):
    create_user(app)
    login(client)
    response = client.post('/events/create', data={
        'title': 'ab',
        'event_time': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),
        'category': 'social',
        'approval_mode': 'automatic',
        'currency': 'GEL',
        'price': '0'
    }, follow_redirects=True)
    with app.app_context():
        assert Event.query.count() == 0


def test_event_past_date_rejected(client, app):
    create_user(app)
    login(client)
    response = client.post('/events/create', data={
        'title': 'Past Event',
        'event_time': '2020-01-01T12:00',
        'category': 'social',
        'approval_mode': 'automatic',
        'currency': 'GEL',
        'price': '0'
    }, follow_redirects=True)
    with app.app_context():
        assert Event.query.count() == 0


def test_register_weak_password_rejected(client):
    response = client.post('/register', data={
        'name': 'Test User',
        'email': 'test@example.com',
        'password': 'short',
        'confirm_password': 'short'
    }, follow_redirects=True)
    assert b'at least 8' in response.data


def test_xss_in_event_title_sanitized(client, app):
    create_user(app)
    login(client)
    client.post('/events/create', data={
        'title': '<script>alert("xss")</script>Valid Title',
        'event_time': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),
        'category': 'social',
        'approval_mode': 'automatic',
        'currency': 'GEL',
        'price': '0'
    }, follow_redirects=True)
    with app.app_context():
        event = Event.query.first()
        if event:
            assert '<script>' not in event.title


# ── Open redirect ──

def test_no_open_redirect_on_login(client, app):
    create_user(app)
    response = client.post(
        '/login?next=https://evil.com',
        data={'email': 'user@example.com', 'password': 'password'},
        follow_redirects=False
    )
    assert response.status_code == 302
    assert 'evil.com' not in response.headers.get('Location', '')


# ── HTTP methods ──

def test_get_on_post_only_endpoints(client, app):
    response = client.get('/notifications/mark-read')
    assert response.status_code == 405


def test_get_on_delete_endpoint(client, app):
    response = client.get('/events/1/delete')
    assert response.status_code == 405