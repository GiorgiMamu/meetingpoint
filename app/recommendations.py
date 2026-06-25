"""
recommendations.py - Event recommendation engine
Implements interest-based and history-based recommendations
"""

from datetime import datetime, timedelta
from app import db
from app.models import Event, User, Participation, Bookmark


def parse_interests(interests_string):
    """Parse comma-separated interests into list."""
    if not interests_string:
        return []
    return [i.strip().lower() for i in interests_string.split(',') if i.strip()]


def parse_mood_tags(mood_tags_string):
    """Parse comma-separated mood tags into list."""
    if not mood_tags_string:
        return []
    return [m.strip().lower() for m in mood_tags_string.split(',') if m.strip()]


def calculate_interest_match_score(user_interests, event_category, event_mood_tags):
    """
    Calculate interest match score (0-100).

    Higher if event category/mood matches user interests.
    """
    if not user_interests:
        return 0

    user_interests_set = set(parse_interests(user_interests))
    event_mood_set = set(parse_mood_tags(event_mood_tags))

    score = 0

    # Category matching (weight: 60%)
    if event_category:
        event_category_lower = event_category.lower()
        for interest in user_interests_set:
            if event_category_lower.startswith(interest[:3]) or interest in event_category_lower:
                score += 60
                break

    # Mood tag matching (weight: 40%)
    if event_mood_set:
        matching_moods = event_mood_set & user_interests_set
        if matching_moods:
            score += min(40, len(matching_moods) * 15)

    return min(100, score)


def calculate_history_match_score(user_id, event):
    """
    Calculate history match score (0-100).

    Based on user's past participation patterns.
    """
    user = User.query.get(user_id)
    if not user:
        return 0

    score = 0

    # Get user's past participations
    past_participations = db.session.query(Event).join(
        Participation
    ).filter(
        Participation.user_id == user_id,
        Participation.status == 'approved',
        Event.event_time < datetime.now()
    ).all()

    if not past_participations:
        return 0

    # Calculate category affinity
    category_counts = {}
    for past_event in past_participations:
        if past_event.category:
            category_counts[past_event.category] = category_counts.get(past_event.category, 0) + 1

    if event.category in category_counts:
        score += 50 * (min(category_counts[event.category], 3) / 3)  # Max 50 points

    # Calculate location proximity affinity
    user_attended_locations = [(e.lat, e.lng) for e in past_participations if e.lat and e.lng]
    if user_attended_locations and event.lat and event.lng:
        # Calculate average distance to past locations
        distances = [
            ((event.lat - loc[0]) ** 2 + (event.lng - loc[1]) ** 2) ** 0.5
            for loc in user_attended_locations
        ]
        avg_distance = sum(distances) / len(distances)

        # Prefer nearby events (max 30 points)
        if avg_distance < 0.1:  # ~10km
            score += 30
        elif avg_distance < 0.5:  # ~50km
            score += 15

    # Time of day affinity
    past_times = [e.event_time.hour for e in past_participations if e.event_time]
    if past_times and event.event_time:
        event_hour = event.event_time.hour
        time_matches = sum(1 for t in past_times if abs(t - event_hour) < 3)

        if time_matches:
            score += min(20, time_matches * 5)  # Max 20 points

    return min(100, score)


def get_recommendations(user_id, limit=10, exclude_bookmarked=True):
    """
    Get event recommendations for a user.

    Combines:
    1. Interest-based recommendations (40% weight)
    2. History-based recommendations (40% weight)
    3. Popularity/recency (20% weight)

    Args:
        user_id: User ID
        limit: Number of recommendations
        exclude_bookmarked: If True, exclude already bookmarked events

    Returns:
        List of Event objects sorted by recommendation score
    """
    user = User.query.get(user_id)
    if not user:
        return []

    # Get user's already joined and bookmarked events
    user_events = db.session.query(Event.id).join(
        Participation
    ).filter(
        Participation.user_id == user_id,
        Event.is_public.is_(True)
    ).all()
    user_event_ids = {e[0] for e in user_events}

    if exclude_bookmarked:
        bookmarked_events = Bookmark.query.filter_by(user_id=user_id).all()
        bookmarked_ids = {b.event_id for b in bookmarked_events}
        user_event_ids.update(bookmarked_ids)

    # Get all public, upcoming events not already joined
    now = datetime.now()
    candidates = Event.query.filter(
        Event.is_public.is_(True),
        Event.is_cancelled.is_(False),
        Event.event_time > now,
        ~Event.id.in_(user_event_ids) if user_event_ids else True
    ).all()

    if not candidates:
        return []

    # Score each event
    scored_events = []

    for event in candidates:
        # Calculate individual scores
        interest_score = calculate_interest_match_score(
            user.interests,
            event.category,
            event.mood_tags
        )

        history_score = calculate_history_match_score(user_id, event)

        # Popularity score (participant count)
        participant_count = Participation.query.filter_by(
            event_id=event.id,
            status='approved'
        ).count()
        popularity_score = min(100, participant_count * 5)

        # Recency bonus (newer events slightly higher)
        days_old = (datetime.now() - event.created_at).days
        recency_score = max(0, 100 - (days_old * 2))

        # Weighted combination
        final_score = (
                interest_score * 0.40 +
                history_score * 0.40 +
                popularity_score * 0.15 +
                recency_score * 0.05
        )

        scored_events.append((event, final_score))

    # Sort by score descending
    scored_events.sort(key=lambda x: x[1], reverse=True)

    return [event for event, score in scored_events[:limit]]


def get_mood_based_suggestions(user_id, limit=6):
    """
    Get mood-based event suggestions for Discover page.

    Returns events matching user interests sorted by mood relevance.
    """
    user = User.query.get(user_id)
    if not user or not user.interests:
        # Return popular upcoming events if user has no interests
        now = datetime.now()
        return Event.query.filter(
            Event.is_public.is_(True),
            Event.is_cancelled.is_(False),
            Event.event_time > now
        ).order_by(Event.created_at.desc()).limit(limit).all()

    user_interests = parse_interests(user.interests)

    # Get events with matching moods or categories
    now = datetime.now()
    matching_events = []

    for interest in user_interests:
        events = Event.query.filter(
            Event.is_public.is_(True),
            Event.is_cancelled.is_(False),
            Event.event_time > now,
            db.or_(
                Event.category.ilike(f'%{interest}%'),
                Event.mood_tags.ilike(f'%{interest}%')
            )
        ).all()
        matching_events.extend(events)

    # Remove duplicates while preserving order
    seen = set()
    unique_events = []
    for event in matching_events:
        if event.id not in seen:
            seen.add(event.id)
            unique_events.append(event)

    return unique_events[:limit]


def get_trending_events(limit=6):
    """
    Get trending events based on recent joins and engagement.

    Used for Discover page suggestions.
    """
    now = datetime.now()
    week_ago = now - timedelta(days=7)

    # Get events with most joins in the last week
    trending = db.session.query(
        Event,
        db.func.count(Participation.id).label('recent_joins')
    ).outerjoin(
        Participation
    ).filter(
        Event.is_public.is_(True),
        Event.is_cancelled.is_(False),
        Event.event_time > now,
        Participation.joined_at >= week_ago
    ).group_by(
        Event.id
    ).order_by(
        db.desc('recent_joins')
    ).limit(limit).all()

    return [event for event, count in trending]
