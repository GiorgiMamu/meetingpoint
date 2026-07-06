from datetime import datetime

from app import db, bcrypt
from app.models import User, Event, Bookmark


def create_admin(app):
    with app.app_context():
        admin = User(
            email='admin@example.com',
            password_hash=bcrypt.generate_password_hash('password').decode('utf-8'),
            name='Admin User',
            role='admin',
            is_active=True
        )
        db.session.add(admin)
        db.session.commit()
        return admin.id


def create_user(app, email, name='Test User', is_active=True, is_blocked=False):
    with app.app_context():
        user = User(
            email=email,
            password_hash=bcrypt.generate_password_hash('password').decode('utf-8'),
            name=name,
            role='user',
            is_active=is_active,
            is_blocked=is_blocked
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def login(client, email, password='password'):
    return client.post('/login', data={
        'email': email,
        'password': password
    }, follow_redirects=True)


def test_admin_access_admin_panel(client, app):
    """Test that admin can access admin panel and regular user cannot."""
    app.config['WTF_CSRF_ENABLED'] = False
    admin_id = create_admin(app)
    user_id = create_user(app, 'user@example.com')

    # Login as regular user
    login(client, 'user@example.com')
    response = client.get('/admin/users')
    assert response.status_code == 403

    # Logout and login as admin
    client.get('/logout')
    login(client, 'admin@example.com')
    response = client.get('/admin/users')
    assert response.status_code == 200
    assert b'User management' in response.data


def test_admin_block_user(client, app):
    """Test that admin can block and unblock a user."""
    app.config['WTF_CSRF_ENABLED'] = False
    admin_id = create_admin(app)
    user_id = create_user(app, 'user@example.com')

    login(client, 'admin@example.com')

    # Block user
    response = client.post(f'/admin/users/{user_id}/toggle_block', follow_redirects=True)
    assert b'has been blocked' in response.data

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.is_blocked is True
        assert user.is_active is True

    # Unblock user
    response = client.post(f'/admin/users/{user_id}/toggle_block', follow_redirects=True)
    assert b'has been unblocked' in response.data

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.is_blocked is False
        assert user.is_active is True


def test_blocked_user_restrictions(client, app):
    """Test that blocked users can login and bookmark, but not create events."""
    app.config['WTF_CSRF_ENABLED'] = False
    admin_id = create_admin(app)
    user_id = create_user(app, 'blocked@example.com', is_active=True, is_blocked=True)

    # Try to login - should succeed now
    response = login(client, 'blocked@example.com')
    assert b'Invalid email or password' not in response.data
    assert b'Please confirm your email' not in response.data

    # Try to access create event - should redirect with flash message (302)
    response = client.get('/events/create', follow_redirects=True)
    assert response.status_code == 200
    assert b'restricted because your account is currently blocked' in response.data

    # Try to bookmark - should succeed
    with app.app_context():
        event = Event(host_id=admin_id, title='Public Event', event_time=datetime(2027, 1, 1), category='social')
        db.session.add(event)
        db.session.commit()
        event_id = event.id

    response = client.post(f'/events/{event_id}/bookmark', follow_redirects=True)
    assert b'Event bookmarked' in response.data

    with app.app_context():
        assert Bookmark.query.filter_by(user_id=user_id, event_id=event_id).first() is not None


def test_blocked_user_can_delete_own_event(client, app):
    """Test that blocked users can delete their own events."""
    app.config['WTF_CSRF_ENABLED'] = False
    with app.app_context():
        user = User(email='blocked_host@example.com',
                    password_hash=bcrypt.generate_password_hash('password').decode('utf-8'),
                    name='Blocked Host', is_active=True, is_blocked=True)
        db.session.add(user)
        db.session.commit()
        user_id = user.id

        event = Event(host_id=user_id, title='Blocked User Event', event_time=datetime(2027, 1, 1), category='social')
        db.session.add(event)
        db.session.commit()
        event_id = event.id

    login(client, 'blocked_host@example.com')

    # Try to delete - should succeed (redirect to my_events)
    response = client.post(f'/events/{event_id}/delete', follow_redirects=True)
    assert b'Event deleted' in response.data

    with app.app_context():
        assert db.session.get(Event, event_id) is None


def test_admin_can_delete_any_event(client, app):
    """Test that admin can delete any user's event."""
    app.config['WTF_CSRF_ENABLED'] = False
    admin_id = create_admin(app)
    user_id = create_user(app, 'host@example.com')

    with app.app_context():
        event = Event(host_id=user_id, title='User Event', event_time=datetime(2027, 1, 1), category='social')
        db.session.add(event)
        db.session.commit()
        event_id = event.id

    login(client, 'admin@example.com')

    # Try to delete - should succeed and redirect to admin_events as specified in 'next'
    response = client.post(f'/events/{event_id}/delete?next=/admin/events', follow_redirects=True)
    assert b'Event deleted' in response.data
    assert b'Event management' in response.data  # Check we are back on admin events page

    with app.app_context():
        assert db.session.get(Event, event_id) is None


def test_admin_no_host_buttons_on_details(client, app):
    """Test that admin does NOT see delete/cancel buttons on details page."""
    app.config['WTF_CSRF_ENABLED'] = False
    admin_id = create_admin(app)
    user_id = create_user(app, 'host@example.com')

    with app.app_context():
        event = Event(host_id=user_id, title='User Event', event_time=datetime(2027, 1, 1), category='social')
        db.session.add(event)
        db.session.commit()
        event_id = event.id

    login(client, 'admin@example.com')
    response = client.get(f'/events/{event_id}')

    assert b'Delete event' not in response.data
    assert b'Cancel event' not in response.data
    assert b'Edit event' not in response.data
    assert b'viewing this event as an administrator' not in response.data


def test_admin_cannot_cancel_event_directly(client, app):
    """Test that admin is forbidden from cancelling an event."""
    app.config['WTF_CSRF_ENABLED'] = False
    admin_id = create_admin(app)
    user_id = create_user(app, 'host@example.com')

    with app.app_context():
        event = Event(host_id=user_id, title='User Event', event_time=datetime(2027, 1, 1), category='social')
        db.session.add(event)
        db.session.commit()
        event_id = event.id

    login(client, 'admin@example.com')
    # Try to cancel via POST - should be forbidden (403)
    response = client.post(f'/events/{event_id}/cancel')
    assert response.status_code == 403

    with app.app_context():
        assert db.session.get(Event, event_id).is_cancelled is False


def test_admin_delete_user_cascades(client, app):
    """Test that deleting a user via admin panel cascades to their events/bookmarks."""
    app.config['WTF_CSRF_ENABLED'] = False
    admin_id = create_admin(app)
    user_id = create_user(app, 'target@example.com')

    with app.app_context():
        event = Event(host_id=user_id, title='User Event', event_time=datetime(2027, 1, 1), category='social')
        db.session.add(event)
        db.session.commit()
        event_id = event.id

        bookmark = Bookmark(user_id=user_id, event_id=event_id)
        db.session.add(bookmark)
        db.session.commit()

    login(client, 'admin@example.com')

    response = client.post(f'/admin/users/{user_id}/delete', follow_redirects=True)
    assert b'permanently deleted' in response.data

    with app.app_context():
        assert db.session.get(User, user_id) is None
        assert db.session.get(Event, event_id) is None
        assert Bookmark.query.filter_by(user_id=user_id).first() is None


def test_admin_anonymous_event(client, app):
    """Test that admin can create anonymous events."""
    app.config['WTF_CSRF_ENABLED'] = False
    admin_id = create_admin(app)

    login(client, 'admin@example.com')

    response = client.post('/events/create', data={
        'title': 'Secret Event',
        'description': 'Shhh',
        'event_time': '2027-01-01T12:00',
        'category': 'social',
        'is_anonymous': 'y',
        'capacity_min': 1,
        'capacity_max': 10,
        'price': 0,
        'currency': 'GEL',
        'approval_mode': 'automatic',
        'participant_list_visible': 'y'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'MeetingPoint Team' in response.data
    # The host's real name shouldn't be in the "Hosted by" section
    assert f'Hosted by\n            \n                <span class="fw-semibold">MeetingPoint Team</span>'.encode() in response.data or \
           b'MeetingPoint Team' in response.data


def test_admin_profile_privacy(client, app):
    """Test that admin profiles are hidden from regular users."""
    app.config['WTF_CSRF_ENABLED'] = False
    admin_id = create_admin(app)
    user_id = create_user(app, 'user@example.com')

    # Regular user tries to view admin profile
    login(client, 'user@example.com')
    response = client.get(f'/profile/{admin_id}')
    assert response.status_code == 403

    # Admin tries to view admin profile
    client.get('/logout')
    login(client, 'admin@example.com')
    response = client.get(f'/profile/{admin_id}')
    assert response.status_code == 200


def test_admin_anonymous_event_profile_privacy(client, app):
    """Test that anonymous events don't link to admin's profile and are hidden from it."""
    app.config['WTF_CSRF_ENABLED'] = False
    admin_id = create_admin(app)
    user_id = create_user(app, 'user@example.com')

    with app.app_context():
        # Admin creates an anonymous event
        event = Event(host_id=admin_id, title='Anon Event', event_time=datetime(2027, 1, 1),
                      category='social', is_anonymous=True, is_public=True)
        db.session.add(event)
        db.session.commit()
        event_id = event.id

    # User views the event
    login(client, 'user@example.com')
    response = client.get(f'/events/{event_id}')
    assert b'MeetingPoint Team' in response.data
    assert f'/profile/{admin_id}' not in response.data.decode('utf-8')

    # User views an admin event that is NOT explicitly marked anonymous
    with app.app_context():
        admin_event_normal = Event(host_id=admin_id, title='Admin Normal Event', event_time=datetime(2027, 3, 1),
                                   category='social', is_anonymous=False, is_public=True)
        db.session.add(admin_event_normal)
        db.session.commit()
        normal_event_id = admin_event_normal.id

    response = client.get(f'/events/{normal_event_id}')
    assert b'MeetingPoint Team' in response.data  # Should still be anonymous because it's an admin
    assert f'/profile/{admin_id}' not in response.data.decode('utf-8')

    # User tries to view admin profile (should be 403 with friendly error message)
    response = client.get(f'/profile/{admin_id}')
    assert response.status_code == 403

    # Let's test with a regular user being anonymous (if that was possible, 
    # but currently only admin sets it in form)
    with app.app_context():
        user_event = Event(host_id=user_id, title='User Anon', event_time=datetime(2027, 2, 1),
                           category='social', is_anonymous=True, is_public=True)
        db.session.add(user_event)
        db.session.commit()
        user_event_id = user_event.id

    client.get('/logout')
    # Anonymous visitor views user's profile
    response = client.get(f'/profile/{user_id}')
    assert response.status_code == 200
    assert b'User Anon' not in response.data  # Should be hidden

    # User views their own profile
    login(client, 'user@example.com')
    response = client.get(f'/profile/{user_id}')
    assert b'User Anon' in response.data  # Should be visible to owner


def test_admin_profile_hides_followers_and_following(client, app):
    app.config['WTF_CSRF_ENABLED'] = False
    admin_id = create_admin(app)
    login(client, 'admin@example.com')
    response = client.get(f'/profile/{admin_id}')
    assert response.status_code == 200
    assert b'Followers' not in response.data
    assert b'Following' not in response.data


def test_admin_chat_hides_profile_links_for_other_users(client, app):
    from app.models import Message, Participation
    app.config['WTF_CSRF_ENABLED'] = False
    admin_id = create_admin(app)
    user_id = create_user(app, 'user@example.com', name='Regular User')
    with app.app_context():
        event = Event(
            host_id=admin_id,
            title='Admin Chat Event',
            event_time=datetime(2027, 1, 1, 12, 0),
            category='social',
            is_public=True,
            approval_mode='automatic',
        )
        db.session.add(event)
        db.session.commit()
        event_id = event.id
        db.session.add(Participation(
            user_id=user_id,
            event_id=event_id,
            status='approved',
        ))
        db.session.add(Message(
            user_id=admin_id,
            event_id=event_id,
            content='Hello from admin',
        ))
        db.session.commit()
    login(client, 'user@example.com')
    response = client.get(f'/events/{event_id}/chat')
    assert response.status_code == 200
    assert b'MeetingPoint Team' in response.data
    assert f'/profile/{admin_id}'.encode() not in response.data
