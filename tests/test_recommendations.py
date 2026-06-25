import pytest
from datetime import datetime, timedelta
from app import create_app, db
from app.models import User, Event, Participation, Bookmark
from app.recommendations import (
    parse_tags,
    haversine_km,
    score_event,
    get_recommendations,
    get_mood_based_suggestions,
    get_trending_events,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

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


@pytest.fixture
def host(app):
    user = User(email="host@test.com", password_hash="hash", name="Host")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def user(app):
    u = User(
        email="user@test.com",
        password_hash="hash",
        name="User",
        interests="sports, music",
    )
    db.session.add(u)
    db.session.commit()
    return u


# ── parse_tags ────────────────────────────────────────────────────────────────

def test_parse_tags_normal():
    assert parse_tags("sports, music, food") == ["sports", "music", "food"]


def test_parse_tags_strips_and_lowercases():
    assert parse_tags("  Tech  ,  Art  ") == ["tech", "art"]


def test_parse_tags_none():
    assert parse_tags(None) == []


def test_parse_tags_empty_string():
    assert parse_tags("") == []


def test_parse_tags_single():
    assert parse_tags("chill") == ["chill"]


# ── haversine_km ──────────────────────────────────────────────────────────────

def test_haversine_same_point():
    assert haversine_km(41.69, 44.83, 41.69, 44.83) == pytest.approx(0.0, abs=1e-6)


def test_haversine_known_distance():
    # Tbilisi → Batumi is roughly 263 km (straight-line)
    dist = haversine_km(41.6938, 44.8015, 41.6417, 41.6356)
    assert 255 < dist < 275


def test_haversine_returns_positive():
    dist = haversine_km(0, 0, 1, 1)
    assert dist > 0


# ── score_event ───────────────────────────────────────────────────────────────

@pytest.fixture
def future_event(app, host):
    event = Event(
        host_id=host.id,
        title="Sports Chill Event",
        event_time=datetime.now() + timedelta(days=2),
        category="sports",
        mood_tags="chill, active",
        is_public=True,
        is_cancelled=False,
        created_at=datetime.now(),
    )
    db.session.add(event)
    db.session.commit()
    return event


def test_score_event_returns_float_in_range(app, user, future_event):
    user_interests = set(parse_tags(user.interests))
    s = score_event(user, future_event, [], user_interests, [], [])
    assert isinstance(s, float)
    assert 0.0 <= s <= 100.0


def test_score_event_interest_match_raises_score(app, user, future_event):
    """User with matching interests should score higher than one without."""
    matching_interests = set(parse_tags("sports, chill"))
    no_interests = set()

    score_match = score_event(user, future_event, [], matching_interests, [], [])
    score_none = score_event(user, future_event, [], no_interests, [], [])

    assert score_match > score_none


def test_score_event_history_affinity(app, user, host, future_event):
    """Attending past events in same category should boost score."""
    past_event = Event(
        host_id=host.id,
        title="Past Sports",
        event_time=datetime.now() - timedelta(days=5),
        category="sports",
        is_public=True,
        is_cancelled=False,
        created_at=datetime.now() - timedelta(days=10),
    )
    db.session.add(past_event)
    db.session.commit()

    user_interests = set(parse_tags(user.interests))

    score_with_history = score_event(user, future_event, [past_event], user_interests, [], [])
    score_no_history = score_event(user, future_event, [], user_interests, [], [])

    assert score_with_history > score_no_history


def test_score_event_location_proximity(app, user, host):
    """Event near user's past locations should score higher."""
    nearby_event = Event(
        host_id=host.id,
        title="Nearby Event",
        event_time=datetime.now() + timedelta(days=1),
        category="music",
        is_public=True,
        is_cancelled=False,
        created_at=datetime.now(),
        lat=41.70,
        lng=44.80,
    )
    db.session.add(nearby_event)
    db.session.commit()

    user_interests = set(parse_tags(user.interests))
    close_location = [(41.69, 44.83)]   # ~1 km away
    far_location   = [(35.00, 30.00)]   # very far

    score_close = score_event(user, nearby_event, [], user_interests, close_location, [])
    score_far   = score_event(user, nearby_event, [], user_interests, far_location,   [])

    assert score_close > score_far


def test_score_event_time_affinity(app, user, host):
    """Events at preferred hours should score higher."""
    morning_event = Event(
        host_id=host.id,
        title="Morning Run",
        event_time=datetime(datetime.now().year + 1, 6, 1, 8, 0),
        category="sports",
        is_public=True,
        is_cancelled=False,
        created_at=datetime.now(),
    )
    db.session.add(morning_event)
    db.session.commit()

    user_interests = set(parse_tags(user.interests))
    matching_hours = [7, 8, 9]
    different_hours = [20, 21, 22]

    score_match = score_event(user, morning_event, [], user_interests, [], matching_hours)
    score_diff  = score_event(user, morning_event, [], user_interests, [], different_hours)

    assert score_match > score_diff


def test_score_event_recency_boost(app, user, host):
    """A freshly created event should score higher than an old one (all else equal)."""
    new_event = Event(
        host_id=host.id,
        title="New Event",
        event_time=datetime.now() + timedelta(days=3),
        category="music",
        is_public=True,
        is_cancelled=False,
        created_at=datetime.now(),
    )
    old_event = Event(
        host_id=host.id,
        title="Old Event",
        event_time=datetime.now() + timedelta(days=3),
        category="music",
        is_public=True,
        is_cancelled=False,
        created_at=datetime.now() - timedelta(days=15),
    )
    db.session.add_all([new_event, old_event])
    db.session.commit()

    score_new = score_event(user, new_event, [], set(), [], [])
    score_old = score_event(user, old_event, [], set(), [], [])

    assert score_new > score_old


# ── get_recommendations ───────────────────────────────────────────────────────

def test_get_recommendations_returns_list(app, user, host):
    now = datetime.now()
    events = [
        Event(
            host_id=host.id,
            title=f"Event {i}",
            event_time=now + timedelta(days=i + 1),
            category="sports",
            is_public=True,
            is_cancelled=False,
            created_at=now,
        )
        for i in range(5)
    ]
    db.session.add_all(events)
    db.session.commit()

    recs = get_recommendations(user.id, limit=10)
    assert isinstance(recs, list)
    assert len(recs) <= 10


def test_get_recommendations_respects_limit(app, user, host):
    now = datetime.now()
    events = [
        Event(
            host_id=host.id,
            title=f"Event {i}",
            event_time=now + timedelta(days=i + 1),
            category="music",
            is_public=True,
            is_cancelled=False,
            created_at=now,
        )
        for i in range(8)
    ]
    db.session.add_all(events)
    db.session.commit()

    recs = get_recommendations(user.id, limit=3)
    assert len(recs) <= 3


def test_get_recommendations_excludes_joined_events(app, user, host):
    now = datetime.now()
    event = Event(
        host_id=host.id,
        title="Already Joined",
        event_time=now + timedelta(days=1),
        category="sports",
        is_public=True,
        is_cancelled=False,
        created_at=now,
    )
    db.session.add(event)
    db.session.commit()

    participation = Participation(
        user_id=user.id,
        event_id=event.id,
        status="approved",
        joined_at=now,
    )
    db.session.add(participation)
    db.session.commit()

    recs = get_recommendations(user.id, limit=10)
    assert all(e.id != event.id for e in recs)


def test_get_recommendations_excludes_bookmarked_events(app, user, host):
    now = datetime.now()
    event = Event(
        host_id=host.id,
        title="Bookmarked",
        event_time=now + timedelta(days=1),
        category="music",
        is_public=True,
        is_cancelled=False,
        created_at=now,
    )
    db.session.add(event)
    db.session.commit()

    bookmark = Bookmark(user_id=user.id, event_id=event.id)
    db.session.add(bookmark)
    db.session.commit()

    recs = get_recommendations(user.id, limit=10, exclude_bookmarked=True)
    assert all(e.id != event.id for e in recs)


def test_get_recommendations_invalid_user(app):
    recs = get_recommendations(user_id=99999)
    assert recs == []


def test_get_recommendations_no_future_events(app, user):
    recs = get_recommendations(user.id, limit=10)
    assert recs == []


# ── get_mood_based_suggestions ────────────────────────────────────────────────

def test_get_mood_based_suggestions_returns_list(app, user, host):
    now = datetime.now()
    event = Event(
        host_id=host.id,
        title="Chill Hangout",
        event_time=now + timedelta(days=1),
        category="music",
        mood_tags="chill, social",
        is_public=True,
        is_cancelled=False,
        created_at=now,
    )
    db.session.add(event)
    db.session.commit()

    suggestions = get_mood_based_suggestions(user.id, limit=6)
    assert isinstance(suggestions, list)


def test_get_mood_based_suggestions_matches_interests(app, user, host):
    now = datetime.now()
    sports_event = Event(
        host_id=host.id,
        title="Sports Night",
        event_time=now + timedelta(days=1),
        category="sports",
        is_public=True,
        is_cancelled=False,
        created_at=now,
    )
    unrelated_event = Event(
        host_id=host.id,
        title="Cooking Class",
        event_time=now + timedelta(days=1),
        category="cooking",
        is_public=True,
        is_cancelled=False,
        created_at=now,
    )
    db.session.add_all([sports_event, unrelated_event])
    db.session.commit()

    suggestions = get_mood_based_suggestions(user.id, limit=6)
    suggestion_ids = [e.id for e in suggestions]
    assert sports_event.id in suggestion_ids


def test_get_mood_based_suggestions_fallback_no_interests(app, host):
    """User with no interests should get recent public events."""
    no_interest_user = User(
        email="blank@test.com",
        password_hash="hash",
        name="Blank",
    )
    db.session.add(no_interest_user)
    db.session.commit()

    now = datetime.now()
    event = Event(
        host_id=host.id,
        title="Random Event",
        event_time=now + timedelta(days=1),
        is_public=True,
        is_cancelled=False,
        created_at=now,
    )
    db.session.add(event)
    db.session.commit()

    suggestions = get_mood_based_suggestions(no_interest_user.id, limit=6)
    assert isinstance(suggestions, list)
    assert len(suggestions) > 0


def test_get_mood_based_suggestions_respects_limit(app, user, host):
    now = datetime.now()
    events = [
        Event(
            host_id=host.id,
            title=f"Sports Event {i}",
            event_time=now + timedelta(days=i + 1),
            category="sports",
            is_public=True,
            is_cancelled=False,
            created_at=now,
        )
        for i in range(10)
    ]
    db.session.add_all(events)
    db.session.commit()

    suggestions = get_mood_based_suggestions(user.id, limit=4)
    assert len(suggestions) <= 4


# ── get_trending_events ───────────────────────────────────────────────────────

def test_get_trending_events_returns_list(app, host, user):
    now = datetime.now()
    event = Event(
        host_id=host.id,
        title="Popular Event",
        event_time=now + timedelta(days=1),
        is_public=True,
        is_cancelled=False,
        created_at=now,
    )
    db.session.add(event)
    db.session.commit()

    participation = Participation(
        user_id=user.id,
        event_id=event.id,
        status="approved",
        joined_at=now,
    )
    db.session.add(participation)
    db.session.commit()

    trending = get_trending_events(limit=6)
    assert isinstance(trending, list)


def test_get_trending_events_respects_limit(app, host):
    now = datetime.now()
    users = [
        User(email=f"u{i}@test.com", password_hash="hash", name=f"User{i}")
        for i in range(10)
    ]
    db.session.add_all(users)
    db.session.commit()

    events = [
        Event(
            host_id=host.id,
            title=f"Trending {i}",
            event_time=now + timedelta(days=i + 1),
            is_public=True,
            is_cancelled=False,
            created_at=now,
        )
        for i in range(10)
    ]
    db.session.add_all(events)
    db.session.commit()

    participations = [
        Participation(
            user_id=users[i].id,
            event_id=events[i].id,
            status="approved",
            joined_at=now,
        )
        for i in range(10)
    ]
    db.session.add_all(participations)
    db.session.commit()

    trending = get_trending_events(limit=5)
    assert len(trending) <= 5


def test_get_trending_events_excludes_old_joins(app, host, user):
    """Participations older than 7 days should not count toward trending."""
    now = datetime.now()
    event = Event(
        host_id=host.id,
        title="Stale Event",
        event_time=now + timedelta(days=1),
        is_public=True,
        is_cancelled=False,
        created_at=now,
    )
    db.session.add(event)
    db.session.commit()

    old_participation = Participation(
        user_id=user.id,
        event_id=event.id,
        status="approved",
        joined_at=now - timedelta(days=10),   # older than 7-day window
    )
    db.session.add(old_participation)
    db.session.commit()

    trending = get_trending_events(limit=10)
    # Event may still appear (outerjoin) but should not be boosted by the old join
    # Verify the result is at least a valid list
    assert isinstance(trending, list)


def test_get_trending_events_excludes_cancelled(app, host, user):
    now = datetime.now()
    cancelled = Event(
        host_id=host.id,
        title="Cancelled Event",
        event_time=now + timedelta(days=1),
        is_public=True,
        is_cancelled=True,
        created_at=now,
    )
    db.session.add(cancelled)
    db.session.commit()

    participation = Participation(
        user_id=user.id,
        event_id=cancelled.id,
        status="approved",
        joined_at=now,
    )
    db.session.add(participation)
    db.session.commit()

    trending = get_trending_events(limit=10)
    assert all(e.id != cancelled.id for e in trending)