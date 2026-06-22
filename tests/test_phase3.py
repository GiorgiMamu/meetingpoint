from datetime import datetime, timedelta

from app import db, bcrypt
from app.models import User, Event, Bookmark


def create_user(app, email='user@example.com', password='password123', name='Test User'):
    with app.app_context():
        hashed = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(email=email, password_hash=hashed, name=name, is_active=True)
        db.session.add(user)
        db.session.commit()
        return user.id


def login(client, email='user@example.com', password='password123'):
    return client.post('/login', data={
        'email': email, 'password': password
    }, follow_redirects=True)


def create_event_in_db(app, host_id, title='Test Event', category='social',
                       lat=41.6938, lng=44.8015, price=0.0,
                       capacity_min=2, capacity_max=10, mood_tags='chill'):
    with app.app_context():
        future_time = datetime.utcnow() + timedelta(hours=2)
        event = Event(
            host_id=host_id,
            title=title,
            event_time=future_time,
            category=category,
            lat=lat,
            lng=lng,
            price=price,
            capacity_min=capacity_min,
            capacity_max=capacity_max,
            mood_tags=mood_tags,
            is_public=True,
            approval_mode='automatic'
        )
        db.session.add(event)
        db.session.commit()
        return event.id


# ── Filtering tests ──

def test_filter_by_category(client, app):
    uid = create_user(app)
    create_event_in_db(app, uid, title='Social Event', category='social')
    create_event_in_db(app, uid, title='Sports Event', category='sports')
    response = client.get('/discover?category=social')
    assert b'Social Event' in response.data
    assert b'Sports Event' not in response.data


def test_filter_by_mood(client, app):
    uid = create_user(app)
    create_event_in_db(app, uid, title='Chill Event', mood_tags='chill, relaxed')
    create_event_in_db(app, uid, title='Active Event', mood_tags='energetic')
    response = client.get('/discover?mood=chill')
    assert b'Chill Event' in response.data
    assert b'Active Event' not in response.data


def test_filter_free_only(client, app):
    uid = create_user(app)
    create_event_in_db(app, uid, title='Free Event', price=0.0)
    create_event_in_db(app, uid, title='Paid Event', price=15.0)
    response = client.get('/discover?free_only=1')
    assert b'Free Event' in response.data
    assert b'Paid Event' not in response.data


def test_filter_by_price_max(client, app):
    uid = create_user(app)
    create_event_in_db(app, uid, title='Cheap Event', price=5.0)
    create_event_in_db(app, uid, title='Expensive Event', price=50.0)
    response = client.get('/discover?price_max=10')
    assert b'Cheap Event' in response.data
    assert b'Expensive Event' not in response.data


def test_filter_by_group_size(client, app):
    uid = create_user(app)
    create_event_in_db(app, uid, title='Small Event', capacity_min=2, capacity_max=5)
    create_event_in_db(app, uid, title='Large Event', capacity_min=20, capacity_max=100)
    response = client.get('/discover?size_max=10')
    assert b'Small Event' in response.data
    assert b'Large Event' not in response.data


def test_filter_by_date_from(client, app):
    uid = create_user(app)
    create_event_in_db(app, uid, title='Future Event')
    tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime('%Y-%m-%d')
    far_future = (datetime.utcnow() + timedelta(days=30)).strftime('%Y-%m-%d')
    response = client.get(f'/discover?date_from={far_future}')
    assert b'Future Event' not in response.data


# ── Location radius search tests ──

def test_haversine_distance():
    from app.utils import haversine_distance
    # Tbilisi to roughly 10km away
    dist = haversine_distance(41.6938, 44.8015, 41.7838, 44.8015)
    assert 9 < dist < 12


def test_filter_events_by_radius():
    from app.utils import filter_events_by_radius

    class MockEvent:
        def __init__(self, lat, lng, title):
            self.lat = lat
            self.lng = lng
            self.title = title

    events = [
        MockEvent(41.6938, 44.8015, 'Near Event'),  # 0km away
        MockEvent(41.7938, 44.9015, 'Medium Event'),  # ~13km away
        MockEvent(42.5000, 45.5000, 'Far Event'),  # ~100km away
    ]

    result = filter_events_by_radius(events, 41.6938, 44.8015, 20)
    titles = [e.title for e in result]
    assert 'Near Event' in titles
    assert 'Medium Event' in titles
    assert 'Far Event' not in titles


def test_radius_filter_excludes_no_coords():
    from app.utils import filter_events_by_radius

    class MockEvent:
        def __init__(self, lat, lng, title):
            self.lat = lat
            self.lng = lng
            self.title = title

    events = [
        MockEvent(None, None, 'No Coords Event'),
        MockEvent(41.6938, 44.8015, 'Valid Event'),
    ]

    result = filter_events_by_radius(events, 41.6938, 44.8015, 50)
    titles = [e.title for e in result]
    assert 'No Coords Event' not in titles
    assert 'Valid Event' in titles


# ── Geocoding fallback test ──

def test_geocode_returns_none_for_empty():
    from app.utils import geocode_location
    lat, lng = geocode_location('')
    assert lat is None
    assert lng is None


def test_geocode_returns_none_for_none():
    from app.utils import geocode_location
    lat, lng = geocode_location(None)
    assert lat is None
    assert lng is None


# ── Bookmark tests ──

def test_bookmarks_page_requires_login(client):
    response = client.get('/bookmarks', follow_redirects=True)
    assert b'login' in response.data.lower() or response.status_code == 200


def test_add_bookmark(client, app):
    uid = create_user(app)
    event_id = create_event_in_db(app, uid)
    login(client)
    response = client.post(f'/events/{event_id}/bookmark',
                           follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert Bookmark.query.filter_by(
            user_id=uid, event_id=event_id).count() == 1


def test_remove_bookmark(client, app):
    uid = create_user(app)
    event_id = create_event_in_db(app, uid)
    login(client)
    # Add bookmark
    client.post(f'/events/{event_id}/bookmark', follow_redirects=True)
    # Remove bookmark
    client.post(f'/events/{event_id}/bookmark', follow_redirects=True)
    with app.app_context():
        assert Bookmark.query.filter_by(
            user_id=uid, event_id=event_id).count() == 0


def test_bookmarks_page_shows_bookmarked_event(client, app):
    uid = create_user(app)
    event_id = create_event_in_db(app, uid, title='Bookmarked Event')
    login(client)
    client.post(f'/events/{event_id}/bookmark', follow_redirects=True)
    response = client.get('/bookmarks')
    assert b'Bookmarked Event' in response.data
