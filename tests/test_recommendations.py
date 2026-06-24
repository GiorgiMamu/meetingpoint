import pytest
from datetime import datetime, timedelta
from app import create_app, db
from app.models import User, Event, Participation, Bookmark
from app.recommendations import (
    calculate_interest_match_score,
    calculate_history_match_score,
    get_recommendations,
    get_mood_based_suggestions,
    get_trending_events,
    parse_interests,
    parse_mood_tags
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


def test_parse_interests():
    """Test parsing comma-separated interests."""
    result = parse_interests("sports, music, food")
    assert result == ["sports", "music", "food"]

    result = parse_interests("  Tech  ,  Art  ")
    assert result == ["tech", "art"]

    assert parse_interests(None) == []
    assert parse_interests("") == []


def test_parse_mood_tags():
    """Test parsing mood tags."""
    result = parse_mood_tags("chill, energetic, social")
    assert result == ["chill", "energetic", "social"]

    assert parse_mood_tags(None) == []


def test_calculate_interest_match_score(app):
    """Test interest matching algorithm."""
    # Perfect match
    score = calculate_interest_match_score("sports", "sports", "active")
    assert score > 0

    # No interests
    score = calculate_interest_match_score(None, "sports", "active")
    assert score == 0

    # Multiple interests matching
    score = calculate_interest_match_score("sports, music", "sports", "live")
    assert score > 0


def test_calculate_history_match_score(app):
    """Test history-based scoring."""
    # Create test user
    user = User(
        email="test@example.com",
        password_hash="hash",
        name="Test User",
        interests="sports,music"
    )
    db.session.add(user)
    db.session.commit()

    # Create past event
    past_event = Event(
        host_id=1,
        title="Past Sports Event",
        event_time=datetime.now() - timedelta(days=7),
        category="sports"
    )
    db.session.add(past_event)
    db.session.commit()

    # Create participation
    participation = Participation(
        user_id=user.id,
        event_id=past_event.id,
        status='approved'
    )
    db.session.add(participation)
    db.session.commit()

    # Test scoring
    score = calculate_history_match_score(user.id, past_event)
    assert isinstance(score, (int, float))
    assert 0 <= score <= 100


def test_get_recommendations(app):
    """Test recommendation engine."""
    # Create users
    host = User(email="host@test.com", password_hash="hash", name="Host")
    user = User(email="user@test.com", password_hash="hash", name="User", interests="sports,music")
    db.session.add_all([host, user])
    db.session.commit()

    # Create events
    now = datetime.now()
    event1 = Event(
        host_id=host.id,
        title="Sports Event",
        event_time=now + timedelta(days=1),
        category="sports",
        is_public=True
    )
    event2 = Event(
        host_id=host.id,
        title="Music Event",
        event_time=now + timedelta(days=2),
        category="music",
        is_public=True
    )
    db.session.add_all([event1, event2])
    db.session.commit()

    # Get recommendations
    recommendations = get_recommendations(user.id, limit=10)
    assert isinstance(recommendations, list)
    assert len(recommendations) <= 10


def test_get_mood_based_suggestions(app):
    """Test mood-based suggestions."""
    user = User(email="test@test.com", password_hash="hash", name="Test", interests="chill,social")
    db.session.add(user)
    db.session.commit()

    now = datetime.now()
    event = Event(
        host_id=1,
        title="Chill Social Event",
        event_time=now + timedelta(days=1),
        mood_tags="chill, social",
        is_public=True
    )
    db.session.add(event)
    db.session.commit()

    suggestions = get_mood_based_suggestions(user.id, limit=6)
    assert isinstance(suggestions, list)


def test_get_trending_events(app):
    """Test trending events retrieval."""
    host = User(email="host@test.com", password_hash="hash", name="Host")
    user = User(email="user@test.com", password_hash="hash", name="User")
    db.session.add_all([host, user])
    db.session.commit()

    now = datetime.now()
    event = Event(
        host_id=host.id,
        title="Popular Event",
        event_time=now + timedelta(days=1),
        is_public=True
    )
    db.session.add(event)
    db.session.commit()

    # Add recent participation
    participation = Participation(
        user_id=user.id,
        event_id=event.id,
        status='approved',
        joined_at=now
    )
    db.session.add(participation)
    db.session.commit()

    trending = get_trending_events(limit=6)
    assert isinstance(trending, list)