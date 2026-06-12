import pytest
from datetime import datetime, timedelta
from app import db, bcrypt
from app.models import User, Event, Participation, Follow, Notification, Message


def create_user(app, email, name='Test User'):
    with app.app_context():
        user = User(
            email=email,
            password_hash=bcrypt.generate_password_hash('password').decode('utf-8'),
            name=name,
            is_active=True
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def login(client, email):
    return client.post('/login', data={
        'email': email, 'password': 'password'
    }, follow_redirects=True)


def create_event(app, host_id, approval_mode='automatic', title='Test Event'):
    with app.app_context():
        event = Event(
            host_id=host_id,
            title=title,
            event_time=datetime.utcnow() + timedelta(days=3),
            category='social',
            is_public=True,
            approval_mode=approval_mode
        )
        db.session.add(event)
        db.session.commit()
        return event.id


# ── Follow / Unfollow ──

def test_follow_user(client, app):
    uid1 = create_user(app, 'user1@example.com')
    uid2 = create_user(app, 'user2@example.com')
    login(client, 'user1@example.com')
    response = client.post(f'/users/{uid2}/follow', follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert Follow.query.filter_by(follower_id=uid1, followed_id=uid2).first() is not None


def test_unfollow_user(client, app):
    uid1 = create_user(app, 'user1@example.com')
    uid2 = create_user(app, 'user2@example.com')
    login(client, 'user1@example.com')
    client.post(f'/users/{uid2}/follow', follow_redirects=True)
    client.post(f'/users/{uid2}/follow', follow_redirects=True)
    with app.app_context():
        assert Follow.query.filter_by(follower_id=uid1, followed_id=uid2).first() is None


def test_cannot_follow_self(client, app):
    uid = create_user(app, 'user@example.com')
    login(client, 'user@example.com')
    response = client.post(f'/users/{uid}/follow', follow_redirects=True)
    assert b'cannot follow yourself' in response.data.lower()
    with app.app_context():
        assert Follow.query.filter_by(follower_id=uid, followed_id=uid).first() is None


def test_follow_creates_notification(client, app):
    uid1 = create_user(app, 'user1@example.com')
    uid2 = create_user(app, 'user2@example.com')
    login(client, 'user1@example.com')
    client.post(f'/users/{uid2}/follow', follow_redirects=True)
    with app.app_context():
        notif = Notification.query.filter_by(user_id=uid2, type='follow').first()
        assert notif is not None


# ── Join / Leave ──

def test_join_automatic_event(client, app):
    host_id = create_user(app, 'host@example.com')
    user_id = create_user(app, 'user@example.com')
    event_id = create_event(app, host_id, approval_mode='automatic')
    login(client, 'user@example.com')
    response = client.post(f'/events/{event_id}/join', follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        p = Participation.query.filter_by(user_id=user_id, event_id=event_id).first()
        assert p is not None
        assert p.status == 'approved'


def test_join_manual_event_creates_pending(client, app):
    host_id = create_user(app, 'host@example.com')
    user_id = create_user(app, 'user@example.com')
    event_id = create_event(app, host_id, approval_mode='manual')
    login(client, 'user@example.com')
    client.post(f'/events/{event_id}/join', follow_redirects=True)
    with app.app_context():
        p = Participation.query.filter_by(user_id=user_id, event_id=event_id).first()
        assert p.status == 'pending'


def test_leave_event(client, app):
    host_id = create_user(app, 'host@example.com')
    user_id = create_user(app, 'user@example.com')
    event_id = create_event(app, host_id)
    login(client, 'user@example.com')
    client.post(f'/events/{event_id}/join', follow_redirects=True)
    client.post(f'/events/{event_id}/leave', follow_redirects=True)
    with app.app_context():
        assert Participation.query.filter_by(user_id=user_id, event_id=event_id).first() is None


def test_cannot_join_twice(client, app):
    host_id = create_user(app, 'host@example.com')
    create_user(app, 'user@example.com')
    event_id = create_event(app, host_id)
    login(client, 'user@example.com')
    client.post(f'/events/{event_id}/join', follow_redirects=True)
    client.post(f'/events/{event_id}/join', follow_redirects=True)
    with app.app_context():
        assert Participation.query.filter_by(event_id=event_id).count() == 1


def test_host_cannot_join_own_event(client, app):
    host_id = create_user(app, 'host@example.com')
    event_id = create_event(app, host_id)
    login(client, 'host@example.com')
    response = client.post(f'/events/{event_id}/join', follow_redirects=True)
    assert b'host' in response.data.lower()
    with app.app_context():
        assert Participation.query.filter_by(event_id=event_id).count() == 0


# ── Approval workflow ──

def test_approve_participant(client, app):
    host_id = create_user(app, 'host@example.com')
    user_id = create_user(app, 'user@example.com')
    event_id = create_event(app, host_id, approval_mode='manual')

    login(client, 'user@example.com')
    client.post(f'/events/{event_id}/join', follow_redirects=True)
    client.get('/logout')

    login(client, 'host@example.com')
    client.post(f'/events/{event_id}/approve/{user_id}', follow_redirects=True)
    with app.app_context():
        p = Participation.query.filter_by(user_id=user_id, event_id=event_id).first()
        assert p.status == 'approved'


def test_decline_participant(client, app):
    host_id = create_user(app, 'host@example.com')
    user_id = create_user(app, 'user@example.com')
    event_id = create_event(app, host_id, approval_mode='manual')

    login(client, 'user@example.com')
    client.post(f'/events/{event_id}/join', follow_redirects=True)
    client.get('/logout')

    login(client, 'host@example.com')
    client.post(f'/events/{event_id}/decline/{user_id}', follow_redirects=True)
    with app.app_context():
        p = Participation.query.filter_by(user_id=user_id, event_id=event_id).first()
        assert p.status == 'declined'


def test_remove_participant(client, app):
    host_id = create_user(app, 'host@example.com')
    user_id = create_user(app, 'user@example.com')
    event_id = create_event(app, host_id)

    login(client, 'user@example.com')
    client.post(f'/events/{event_id}/join', follow_redirects=True)
    client.get('/logout')

    login(client, 'host@example.com')
    client.post(f'/events/{event_id}/remove/{user_id}', follow_redirects=True)
    with app.app_context():
        assert Participation.query.filter_by(user_id=user_id, event_id=event_id).first() is None


# ── Invitation ──

def test_invite_user(client, app):
    host_id = create_user(app, 'host@example.com')
    user_id = create_user(app, 'user@example.com')
    event_id = create_event(app, host_id)
    login(client, 'host@example.com')
    client.post(f'/events/{event_id}/invite/{user_id}', follow_redirects=True)
    with app.app_context():
        notif = Notification.query.filter_by(
            user_id=user_id, type='invitation', related_event_id=event_id
        ).first()
        assert notif is not None


def test_cannot_invite_twice(client, app):
    host_id = create_user(app, 'host@example.com')
    user_id = create_user(app, 'user@example.com')
    event_id = create_event(app, host_id)
    login(client, 'host@example.com')
    client.post(f'/events/{event_id}/invite/{user_id}', follow_redirects=True)
    client.post(f'/events/{event_id}/invite/{user_id}', follow_redirects=True)
    with app.app_context():
        count = Notification.query.filter_by(
            user_id=user_id, type='invitation', related_event_id=event_id
        ).count()
        assert count == 1


# ── Chat persistence ──

def test_chat_page_requires_participation(client, app):
    host_id = create_user(app, 'host@example.com')
    create_user(app, 'user@example.com')
    event_id = create_event(app, host_id)
    login(client, 'user@example.com')
    response = client.get(f'/events/{event_id}/chat', follow_redirects=True)
    assert b'must be an approved participant' in response.data


def test_host_can_access_chat(client, app):
    host_id = create_user(app, 'host@example.com')
    event_id = create_event(app, host_id)
    login(client, 'host@example.com')
    response = client.get(f'/events/{event_id}/chat')
    assert response.status_code == 200


def test_notifications_page(client, app):
    uid = create_user(app, 'user@example.com')
    login(client, 'user@example.com')
    response = client.get('/notifications')
    assert response.status_code == 200


# ── Email triggers (smoke tests — no actual emails sent in testing) ──

def test_join_automatic_sends_no_crash(client, app):
    host_id = create_user(app, 'host@example.com')
    create_user(app, 'user@example.com')
    event_id = create_event(app, host_id, approval_mode='automatic')
    login(client, 'user@example.com')
    response = client.post(f'/events/{event_id}/join', follow_redirects=True)
    assert response.status_code == 200


def test_approval_sends_no_crash(client, app):
    host_id = create_user(app, 'host@example.com')
    user_id = create_user(app, 'user@example.com')
    event_id = create_event(app, host_id, approval_mode='manual')
    login(client, 'user@example.com')
    client.post(f'/events/{event_id}/join', follow_redirects=True)
    client.get('/logout')
    login(client, 'host@example.com')
    response = client.post(f'/events/{event_id}/approve/{user_id}', follow_redirects=True)
    assert response.status_code == 200