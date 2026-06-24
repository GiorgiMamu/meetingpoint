import pytest
from datetime import datetime, timedelta
import base64
from app import create_app, db
from app.models import User, Event, Participation
from app.analytics import (
    get_event_analytics,
    get_host_dashboard_metrics,
    calculate_system_metrics
)


@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_get_event_analytics(app):
    """Test event analytics calculation."""
    # Create host and event
    host = User(email="host@test.com", password_hash="hash", name="Host")
    db.session.add(host)
    db.session.commit()

    now = datetime.now()
    event = Event(
        host_id=host.id,
        title="Test Event",
        event_time=now + timedelta(days=1),
        capacity_max=20
    )
    db.session.add(event)
    db.session.commit()

    # Add participants
    for i in range(5):
        user = User(email=f"user{i}@test.com", password_hash="hash", name=f"User {i}")
        db.session.add(user)
    db.session.commit()

    users = User.query.filter(User.email.like('user%')).all()
    for i, user in enumerate(users):
        status = 'approved' if i < 3 else 'pending'
        p = Participation(user_id=user.id, event_id=event.id, status=status)
        db.session.add(p)
    db.session.commit()

    # Get analytics
    analytics = get_event_analytics(event.id)

    assert analytics is not None
    assert analytics['event_id'] == event.id
    assert analytics['total_participants'] == 5
    assert analytics['approved_count'] == 3
    assert analytics['pending_count'] == 2
    assert analytics['attendance_rate'] == 15.0  # 3/20
    assert isinstance(analytics['join_trend_chart'], (str, type(None)))


def test_get_host_dashboard_metrics(app):
    """Test host dashboard metrics."""
    host = User(email="host@test.com", password_hash="hash", name="Host")
    db.session.add(host)
    db.session.commit()

    now = datetime.now()
    event = Event(
        host_id=host.id,
        title="Test Event",
        event_time=now + timedelta(days=1),
        capacity_max=10
    )
    db.session.add(event)
    db.session.commit()

    metrics = get_host_dashboard_metrics(host.id)

    assert metrics['total_events'] == 1
    assert metrics['total_participants'] == 0
    assert metrics['avg_attendance_rate'] == 0.0


def test_calculate_system_metrics(app):
    """Test system-wide metrics calculation."""
    # Create test data
    host = User(email="host@test.com", password_hash="hash", name="Host")
    user = User(email="user@test.com", password_hash="hash", name="User")
    db.session.add_all([host, user])
    db.session.commit()

    now = datetime.now()
    event = Event(
        host_id=host.id,
        title="Test Event",
        event_time=now + timedelta(days=1)
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

    metrics = calculate_system_metrics()

    assert metrics['total_users'] >= 2
    assert metrics['total_events'] >= 1
    assert metrics['total_participations'] >= 1


def test_attendance_rate_calculation(app):
    """Test attendance rate calculation accuracy."""
    host = User(email="host@test.com", password_hash="hash", name="Host")
    db.session.add(host)
    db.session.commit()

    now = datetime.now()
    event = Event(
        host_id=host.id,
        title="Test Event",
        event_time=now + timedelta(days=1),
        capacity_max=100
    )
    db.session.add(event)
    db.session.commit()

    # Add exactly 50 approved participants
    for i in range(50):
        user = User(email=f"user{i}@test.com", password_hash="hash", name=f"User {i}")
        db.session.add(user)
    db.session.commit()

    users = User.query.filter(User.email.like('user%')).all()
    for user in users:
        p = Participation(user_id=user.id, event_id=event.id, status='approved')
        db.session.add(p)
    db.session.commit()

    analytics = get_event_analytics(event.id)

    assert analytics['attendance_rate'] == 50.0  # 50/100