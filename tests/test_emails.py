from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app import db, bcrypt
from app.models import User, Event, Participation
from app.scheduler import send_reminders
from app.utils import (
    send_email,
    send_verification_email,
    send_password_reset_email,
    send_cancellation_emails,
)


def create_user(app, email='user@example.com', name='Test User', active=True):
    with app.app_context():
        user = User(
            email=email,
            password_hash=bcrypt.generate_password_hash('password').decode('utf-8'),
            name=name,
            is_active=active,
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def create_event(app, host_id, title='Test Event', approval_mode='automatic'):
    with app.app_context():
        event = Event(
            host_id=host_id,
            title=title,
            event_time=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=24) + timedelta(days=3),
            category='social',
            is_public=True,
            approval_mode=approval_mode,
        )
        db.session.add(event)
        db.session.commit()
        return event.id


def login(client, email='user@example.com', password='password'):
    return client.post('/login', data={
        'email': email,
        'password': password,
    }, follow_redirects=True)


@pytest.fixture
def mail_sender(app):
    app.config['MAIL_USERNAME'] = 'noreply@meetingpoint.test'


def test_send_email_builds_message(app, mail_sender):
    with app.app_context():
        msg = send_email('user@example.com', 'Test Subject', 'Hello body')
        assert msg.recipients == ['user@example.com']
        assert msg.subject == 'Test Subject'
        assert msg.body == 'Hello body'
        assert msg.sender == 'noreply@meetingpoint.test'


def test_send_email_calls_mail_send_outside_testing(app, mail_sender):
    with app.app_context():
        app.config['TESTING'] = False
        with patch('app.utils.mail.send') as mock_send:
            send_email('user@example.com', 'Subject', 'Body')
            mock_send.assert_called_once()
        app.config['TESTING'] = True


def test_send_email_skips_mail_send_in_testing(app, mail_sender):
    with app.app_context():
        with patch('app.utils.mail.send') as mock_send:
            send_email('user@example.com', 'Subject', 'Body')
            mock_send.assert_not_called()


def test_send_verification_email_content(app, mail_sender):
    with app.app_context():
        user = User(
            email='alice@example.com',
            password_hash='hash',
            name='Alice',
            is_active=False,
        )
        msg = send_verification_email(user)
        assert msg.recipients == ['alice@example.com']
        assert 'Confirm your email' in msg.subject
        assert 'Alice' in msg.body
        assert 'confirm' in msg.body.lower()


def test_send_password_reset_email_content(app, mail_sender):
    with app.app_context():
        user = User(
            email='bob@example.com',
            password_hash='hash',
            name='Bob',
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        msg = send_password_reset_email(user)
        assert msg.recipients == ['bob@example.com']
        assert 'Password reset' in msg.subject
        assert 'Bob' in msg.body
        assert 'reset' in msg.body.lower()
        assert user.password_reset_token is not None


def test_send_cancellation_emails_content(app, mail_sender):
    with app.app_context():
        host = User(
            email='host@example.com',
            password_hash='hash',
            name='Host',
            is_active=True,
        )
        guest = User(
            email='guest@example.com',
            password_hash='hash',
            name='Guest',
            is_active=True,
        )
        db.session.add_all([host, guest])
        db.session.commit()
        event = Event(
            host_id=host.id,
            title='Cancelled Party',
            event_time=datetime(2027, 6, 1, 18, 0),
            category='social',
            is_public=True,
        )
        db.session.add(event)
        db.session.commit()
        participation = Participation(
            user_id=guest.id,
            event_id=event.id,
            status='approved',
        )
        db.session.add(participation)
        db.session.commit()
        participation = Participation.query.filter_by(
            user_id=guest.id,
            event_id=event.id,
        ).first()
        messages = send_cancellation_emails(event, [participation])
        assert len(messages) == 1
        msg = messages[0]
        assert msg.recipients == ['guest@example.com']
        assert 'Event cancelled' in msg.subject
        assert 'Cancelled Party' in msg.body
        assert 'Guest' in msg.body


@patch('app.utils.mail.send')
def test_register_sends_verification_email(mock_send, client, app, mail_sender):
    with app.app_context():
        app.config['TESTING'] = False
    client.post('/register', data={
        'name': 'Alice',
        'email': 'alice@example.com',
        'password': 'securepass1',
        'confirm_password': 'securepass1',
    }, follow_redirects=True)
    mock_send.assert_called_once()
    msg = mock_send.call_args[0][0]
    assert msg.recipients == ['alice@example.com']
    assert 'Confirm your email' in msg.subject


@patch('app.utils.mail.send')
def test_password_reset_sends_email(mock_send, client, app, mail_sender):
    create_user(app, email='reset@example.com')
    with app.app_context():
        app.config['TESTING'] = False
    client.post('/reset-password', data={'email': 'reset@example.com'}, follow_redirects=True)
    mock_send.assert_called_once()
    msg = mock_send.call_args[0][0]
    assert msg.recipients == ['reset@example.com']
    assert 'Password reset' in msg.subject


@patch('app.utils.send_email')
def test_join_automatic_event_sends_email(mock_send, client, app):
    host_id = create_user(app, 'host@example.com')
    create_user(app, 'user@example.com')
    event_id = create_event(app, host_id, approval_mode='automatic')
    login(client, 'user@example.com')
    client.post(f'/events/{event_id}/join', follow_redirects=True)
    mock_send.assert_called_once()
    assert mock_send.call_args[0][0] == 'user@example.com'
    assert 'joined' in mock_send.call_args[0][1].lower()


@patch('app.utils.send_email')
def test_approve_participant_sends_email(mock_send, client, app):
    host_id = create_user(app, 'host@example.com')
    user_id = create_user(app, 'user@example.com')
    event_id = create_event(app, host_id, approval_mode='manual')
    login(client, 'user@example.com')
    client.post(f'/events/{event_id}/join', follow_redirects=True)
    client.get('/logout')
    login(client, 'host@example.com')
    client.post(f'/events/{event_id}/approve/{user_id}', follow_redirects=True)
    mock_send.assert_called_once()
    assert mock_send.call_args[0][0] == 'user@example.com'
    assert 'approved' in mock_send.call_args[0][1].lower()


@patch('app.utils.send_email')
def test_invite_user_sends_email(mock_send, client, app):
    host_id = create_user(app, 'host@example.com', name='Host')
    user_id = create_user(app, 'user@example.com', name='Guest')
    event_id = create_event(app, host_id, title='Invite Event')
    login(client, 'host@example.com')
    client.post(f'/events/{event_id}/invite/{user_id}', follow_redirects=True)
    mock_send.assert_called_once()
    assert mock_send.call_args[0][0] == 'user@example.com'
    assert 'invited' in mock_send.call_args[0][1].lower()
    assert 'Invite Event' in mock_send.call_args[0][2]


@patch('app.utils.send_email')
def test_delete_event_sends_cancellation_emails(mock_send, client, app):
    host_id = create_user(app, 'host@example.com')
    user_id = create_user(app, 'user@example.com')
    event_id = create_event(app, host_id, title='Delete Me')
    with app.app_context():
        db.session.add(Participation(
            user_id=user_id,
            event_id=event_id,
            status='approved',
        ))
        db.session.commit()
    login(client, 'host@example.com')
    client.post(f'/events/{event_id}/delete', follow_redirects=True)
    mock_send.assert_called_once()
    assert mock_send.call_args[0][0] == 'user@example.com'
    assert 'cancelled' in mock_send.call_args[0][1].lower()


@patch('app.utils.send_email')
def test_send_reminders_sends_email_once(mock_send, app):
    with app.app_context():
        host = User(
            email='host@example.com',
            password_hash=bcrypt.generate_password_hash('password').decode('utf-8'),
            name='Host',
            is_active=True,
        )
        user = User(
            email='user@example.com',
            password_hash=bcrypt.generate_password_hash('password').decode('utf-8'),
            name='User',
            is_active=True,
        )
        db.session.add_all([host, user])
        db.session.commit()

        event = Event(
            host_id=host.id,
            title='Reminder Event',
            event_time=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=24),
            category='social',
            is_public=True,
        )
        db.session.add(event)
        db.session.commit()

        db.session.add(Participation(
            user_id=user.id,
            event_id=event.id,
            status='approved',
        ))
        db.session.commit()

        send_reminders(app)
        send_reminders(app)

        assert mock_send.call_count == 1
        assert mock_send.call_args[0][0] == 'user@example.com'
        assert 'Reminder' in mock_send.call_args[0][1]
