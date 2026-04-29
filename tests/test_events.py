import pytest
from app import db, bcrypt
from app.models import User, Event, Participation
from datetime import datetime, timedelta
import io

def create_user(app, email='host@example.com', password='password123', name='Host User'):
    with app.app_context():
        hashed = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(email=email, password_hash=hashed, name=name, is_active=True)
        db.session.add(user)
        db.session.commit()
        return user.id


def login(client, email='host@example.com', password='password123'):
    return client.post('/login', data={
        'email': email, 'password': password
    }, follow_redirects=True)


def create_event_data(future_minutes=60):
    future_time = (datetime.utcnow() + timedelta(minutes=future_minutes))
    return {
        'title': 'Test Event',
        'description': 'A test event',
        'event_time': future_time.strftime('%Y-%m-%dT%H:%M'),
        'location_text': 'Tbilisi',
        'category': 'social',
        'mood_tags': 'fun, casual',
        'capacity_min': '2',
        'capacity_max': '10',
        'price': '0',
        'approval_mode': 'automatic',
        'is_public': 'y',
        'participant_list_visible': 'y'
    }


# --- Create ---
def test_create_event_page_loads(client, app):
    create_user(app)
    login(client)
    response = client.get('/events/create')
    assert response.status_code == 200


def test_create_event_success(client, app):
    create_user(app)
    login(client)
    response = client.post('/events/create',
                           data=create_event_data(),
                           follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert Event.query.count() == 1


def test_create_event_missing_title(client, app):
    create_user(app)
    login(client)
    data = create_event_data()
    data['title'] = ''
    response = client.post('/events/create', data=data, follow_redirects=True)
    with app.app_context():
        assert Event.query.count() == 0


def test_create_event_requires_login(client):
    response = client.get('/events/create', follow_redirects=True)
    assert b'login' in response.data.lower()


# --- Read ---
def test_event_detail_page(client, app):
    create_user(app)
    login(client)
    client.post('/events/create', data=create_event_data(), follow_redirects=True)
    with app.app_context():
        event = Event.query.first()
    response = client.get(f'/events/{event.id}')
    assert response.status_code == 200
    assert b'Test Event' in response.data


# --- Edit ---
def test_edit_event(client, app):
    create_user(app)
    login(client)
    client.post('/events/create', data=create_event_data(), follow_redirects=True)
    with app.app_context():
        event = Event.query.first()
    data = create_event_data()
    data['title'] = 'Updated Title'
    response = client.post(f'/events/{event.id}/edit',
                           data=data, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert Event.query.first().title == 'Updated Title'


# --- Delete ---
def test_delete_event(client, app):
    create_user(app)
    login(client)
    client.post('/events/create', data=create_event_data(), follow_redirects=True)
    with app.app_context():
        event = Event.query.first()
    response = client.post(f'/events/{event.id}/delete', follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert Event.query.count() == 0


# --- Discover / Search ---
def test_discover_page_loads(client):
    response = client.get('/discover')
    assert response.status_code == 200


def test_search_by_keyword(client, app):
    create_user(app)
    login(client)
    client.post('/events/create', data=create_event_data(), follow_redirects=True)
    response = client.get('/discover?q=Test')
    assert b'Test Event' in response.data


def test_search_by_category(client, app):
    create_user(app)
    login(client)
    client.post('/events/create', data=create_event_data(), follow_redirects=True)
    response = client.get('/discover?category=social')
    assert b'Test Event' in response.data


def test_search_no_results(client, app):
    create_user(app)
    login(client)
    client.post('/events/create', data=create_event_data(), follow_redirects=True)
    response = client.get('/discover?q=nonexistentxyz')
    assert b'No events found' in response.data


# --- My Events ---
def test_my_events_page(client, app):
    create_user(app)
    login(client)
    client.post('/events/create', data=create_event_data(), follow_redirects=True)
    response = client.get('/my-events')
    assert b'Test Event' in response.data


# --- History ---
def test_history_page_loads(client, app):
    create_user(app)
    login(client)
    response = client.get('/history')
    assert response.status_code == 200


# --- Profile ---
def test_profile_page_loads(client, app):
    uid = create_user(app)
    login(client)
    response = client.get(f'/profile/{uid}')
    assert response.status_code == 200


def test_edit_profile(client, app):
    create_user(app)
    login(client)
    response = client.post('/profile/edit', data={
        'name': 'Updated Name',
        'bio': 'My bio',
        'location': 'Tbilisi',
        'interests': 'hiking, music',
        'is_profile_public': 'y',
    }, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(email='host@example.com').first()
        assert user.name == 'Updated Name'


# --- Privacy controls ---
def test_private_profile_blocked(client, app):
    uid = create_user(app, email='private@example.com')
    with app.app_context():
        user = User.query.get(uid)
        user.is_profile_public = False
        db.session.commit()
    response = client.get(f'/profile/{uid}', follow_redirects=True)
    assert response.status_code == 403


def test_private_event_blocked(client, app):
    create_user(app)
    login(client)
    data = create_event_data()
    data.pop('is_public')  # make it private
    client.post('/events/create', data=data, follow_redirects=True)
    client.get('/logout')
    with app.app_context():
        event = Event.query.first()
    response = client.get(f'/events/{event.id}')
    assert response.status_code == 403

def test_image_upload_rejected_non_image(client, app):
    create_user(app)
    login(client)
    data = create_event_data()
    data['photo'] = (io.BytesIO(b'not an image'), 'test.txt')
    response = client.post('/events/create',
                           data=data,
                           content_type='multipart/form-data',
                           follow_redirects=True)
    with app.app_context():
        assert Event.query.count() == 0