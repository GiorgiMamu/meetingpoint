from datetime import datetime, timedelta

from app import db, bcrypt
from app.models import User, Event, Participation, Follow, Notification
from app.scheduler import send_reminders


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
            event_time=datetime.now() + timedelta(days=3),
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
        assert notif.actor_user_id == uid1


def test_notifications_mark_all_read(client, app):
    uid1 = create_user(app, 'user1@example.com')
    uid2 = create_user(app, 'user2@example.com')
    login(client, 'user1@example.com')
    client.post(f'/users/{uid2}/follow', follow_redirects=True)
    client.get('/logout')
    login(client, 'user2@example.com')

    response = client.get('/notifications')
    assert b'Mark all as read' in response.data

    client.post('/notifications/mark-read', follow_redirects=True)
    with app.app_context():
        notif = Notification.query.filter_by(user_id=uid2, type='follow').first()
        assert notif.is_read is True


def test_clear_notifications(client, app):
    uid1 = create_user(app, 'user1@example.com')
    uid2 = create_user(app, 'user2@example.com')
    login(client, 'user1@example.com')
    client.post(f'/users/{uid2}/follow', follow_redirects=True)
    client.get('/logout')
    login(client, 'user2@example.com')
    client.post('/notifications/clear', follow_redirects=True)
    response = client.get('/notifications')
    assert b'No notifications' in response.data
    assert b"You're all caught up." in response.data
    with app.app_context():
        assert Notification.query.filter_by(user_id=uid2).count() == 0


def test_profile_followers_page(client, app):
    uid1 = create_user(app, 'user1@example.com')
    uid2 = create_user(app, 'user2@example.com')
    login(client, 'user1@example.com')
    client.post(f'/users/{uid2}/follow', follow_redirects=True)
    response = client.get(f'/profile/{uid2}/followers')
    assert response.status_code == 200
    assert b'user1@example.com' not in response.data
    assert b'followers' in response.data.lower()


def test_profile_following_page(client, app):
    uid1 = create_user(app, 'user1@example.com', name='User One')
    uid2 = create_user(app, 'user2@example.com', name='User Two')
    login(client, 'user1@example.com')
    client.post(f'/users/{uid2}/follow', follow_redirects=True)
    response = client.get(f'/profile/{uid1}/following')
    assert response.status_code == 200
    assert b'User Two' in response.data
    assert b'following' in response.data.lower()


def test_following_excludes_admin(client, app):
    from app.models import Follow
    uid1 = create_user(app, 'user1@example.com', name='User One')
    with app.app_context():
        admin = User(
            email='admin@example.com',
            password_hash=bcrypt.generate_password_hash('password').decode('utf-8'),
            name='Admin User',
            role='admin',
            is_active=True,
        )
        db.session.add(admin)
        db.session.commit()
        db.session.add(Follow(follower_id=uid1, followed_id=admin.id))
        db.session.commit()
    login(client, 'user1@example.com')
    response = client.get(f'/profile/{uid1}/following')
    assert response.status_code == 200
    assert b'Not following anyone yet' in response.data
    assert b'Admin User' not in response.data


def test_share_event_to_follower(client, app):
    host_id = create_user(app, 'host@example.com')
    follower_id = create_user(app, 'follower@example.com')
    event_id = create_event(app, host_id)
    client.get('/logout')
    login(client, 'host@example.com')
    client.post(f'/users/{follower_id}/follow', follow_redirects=True)
    client.post(f'/events/{event_id}/invite/{follower_id}', follow_redirects=True)
    client.get('/logout')
    login(client, 'follower@example.com')
    response = client.get('/notifications')
    assert b'View event' in response.data
    assert b'View profile' in response.data
    with app.app_context():
        notif = Notification.query.filter_by(
            user_id=follower_id, type='invitation', related_event_id=event_id
        ).first()
        assert notif is not None
        assert notif.actor_user_id == host_id


def test_share_event_to_follower_invite_only_event_allowed_for_host(client, app):
    app.config['WTF_CSRF_ENABLED'] = False
    host_id = create_user(app, 'host@example.com')
    follower_id = create_user(app, 'follower@example.com')
    event_id = create_event(app, host_id, approval_mode='manual')
    login(client, 'follower@example.com')
    client.post(f'/users/{host_id}/follow', follow_redirects=True)
    # User first joins the event (creates pending participation for manual approval)
    client.post(f'/events/{event_id}/join', follow_redirects=True)
    client.get('/logout')
    login(client, 'host@example.com')
    response = client.post(f'/events/{event_id}/share-to-follower/{follower_id}')
    assert response.status_code == 302  # Redirect after successful invitation
    with app.app_context():
        notif = Notification.query.filter_by(
            user_id=follower_id, type='invitation', related_event_id=event_id
        ).first()
        assert notif is not None
        # Verify that invited user bypasses manual approval and gets approved status
        participation = Participation.query.filter_by(
            user_id=follower_id, event_id=event_id
        ).first()
        assert participation is not None
        assert participation.status == 'approved'


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


def test_send_reminders_creates_notification_once(app):
    with app.app_context():
        host = User(
            email='host@example.com',
            password_hash=bcrypt.generate_password_hash('password').decode('utf-8'),
            name='Host',
            is_active=True
        )
        user = User(
            email='user@example.com',
            password_hash=bcrypt.generate_password_hash('password').decode('utf-8'),
            name='User',
            is_active=True
        )
        db.session.add_all([host, user])
        db.session.commit()

        event = Event(
            host_id=host.id,
            title='Reminder Event',
            event_time=datetime.now() + timedelta(hours=24),
            category='social',
            is_public=True
        )
        db.session.add(event)
        db.session.commit()

        participation = Participation(
            user_id=user.id,
            event_id=event.id,
            status='approved'
        )
        db.session.add(participation)
        db.session.commit()

        send_reminders(app)
        send_reminders(app)

        notifications = Notification.query.filter_by(
            user_id=user.id,
            type='reminder',
            related_event_id=event.id
        ).all()
        assert len(notifications) == 1


def test_share_event_to_follower_cannot_invite_twice(client, app):
    app.config['WTF_CSRF_ENABLED'] = False
    host_id = create_user(app, 'host@example.com')
    follower_id = create_user(app, 'follower@example.com')
    event_id = create_event(app, host_id)
    login(client, 'follower@example.com')
    client.post(f'/users/{host_id}/follow', follow_redirects=True)
    client.get('/logout')
    login(client, 'host@example.com')
    client.post(f'/events/{event_id}/share-to-follower/{follower_id}', follow_redirects=True)
    response = client.post(f'/events/{event_id}/share-to-follower/{follower_id}', follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        count = Notification.query.filter_by(
            user_id=follower_id, type='invitation', related_event_id=event_id
        ).count()
        assert count == 1


def test_invited_user_can_view_private_event(client, app):
    host_id = create_user(app, 'host@example.com')
    follower_id = create_user(app, 'follower@example.com')
    with app.app_context():
        event = Event(
            host_id=host_id,
            title='Private Event',
            event_time=datetime.now() + timedelta(days=3),
            category='social',
            is_public=False,
            approval_mode='manual'
        )
        db.session.add(event)
        db.session.commit()
        event_id = event.id
    login(client, 'follower@example.com')
    client.post(f'/users/{host_id}/follow', follow_redirects=True)
    client.get('/logout')
    login(client, 'host@example.com')
    client.post(f'/events/{event_id}/share-to-follower/{follower_id}', follow_redirects=True)
    client.get('/logout')
    login(client, 'follower@example.com')
    response = client.get(f'/events/{event_id}')
    assert response.status_code == 200
    assert b'Private Event' in response.data


def test_can_reinvite_after_user_leaves(client, app):
    app.config['WTF_CSRF_ENABLED'] = False
    host_id = create_user(app, 'host@example.com')
    follower_id = create_user(app, 'follower@example.com')
    event_id = create_event(app, host_id)
    login(client, 'follower@example.com')
    client.post(f'/users/{host_id}/follow', follow_redirects=True)
    client.post(f'/events/{event_id}/join', follow_redirects=True)
    client.get('/logout')
    login(client, 'host@example.com')
    client.post(f'/events/{event_id}/share-to-follower/{follower_id}', follow_redirects=True)
    client.get('/logout')
    login(client, 'follower@example.com')
    client.post(f'/events/{event_id}/leave', follow_redirects=True)
    client.get('/logout')
    login(client, 'host@example.com')
    response = client.post(f'/events/{event_id}/share-to-follower/{follower_id}', follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        # Old invitation was cleared on leave; this is a fresh one, not a duplicate.
        count = Notification.query.filter_by(
            user_id=follower_id, type='invitation', related_event_id=event_id
        ).count()
        assert count == 1
        notif = Notification.query.filter_by(
            user_id=follower_id, type='invitation', related_event_id=event_id
        ).first()
        assert notif.actor_user_id == host_id


def test_notification_displays_ampersand(client, app):
    host_id = create_user(app, 'host@example.com')
    follower_id = create_user(app, 'follower@example.com')
    event_id = create_event(app, host_id, title='Food & Drinks Night')
    login(client, 'follower@example.com')
    client.post(f'/users/{host_id}/follow', follow_redirects=True)
    client.get('/logout')
    login(client, 'host@example.com')
    client.post(f'/events/{event_id}/share-to-follower/{follower_id}', follow_redirects=True)
    client.get('/logout')
    login(client, 'follower@example.com')
    response = client.get('/notifications')
    assert b'Food &amp; Drinks Night' in response.data
    assert b'Food &amp;amp; Drinks Night' not in response.data
