"""
recommendations.py - Event recommendation engine
Implements interest-based, history-based, location and time recommendations
"""

from datetime import datetime, timedelta

from app import db
from app.models import Event, User, Participation, Bookmark


def parse_tags(text):
    """Parse comma-separated tags into lowercase list."""
    if not text:
        return []
    return [t.strip().lower() for t in text.split(',') if t.strip()]


def haversine_km(lat1, lng1, lat2, lng2):
    """Calculate distance in km between two coordinates."""
    import math
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def score_event(user, event, past_events, user_interests, user_locations, user_hours):
    """
    Score a single event for a user. Returns float 0-100.

    Scoring breakdown:
    - Interest / mood tag match   : up to 35 points
    - History category affinity   : up to 25 points
    - Location proximity          : up to 20 points
    - Time-of-day affinity        : up to 10 points
    - Recency (newly created)     : up to 10 points
    """
    score = 0.0

    # ── 1. Interest / mood tag match (35 pts) ──────────────────────────────
    event_tags = set(parse_tags(event.mood_tags))
    event_category_words = set(parse_tags(event.category.replace(' ', ',')))
    combined_event_tags = event_tags | event_category_words

    if user_interests and combined_event_tags:
        exact_matches = user_interests & combined_event_tags

        # Only count a partial/substring match for pairs that are NOT
        # already counted as an exact match, so a single matching tag
        # can't score in both buckets at once.
        partial = 0
        for ui in user_interests:
            for et in combined_event_tags:
                if ui == et:
                    continue  # already counted in exact_matches
                if ui in et or et in ui:
                    partial += 1

        score += min(35, len(exact_matches) * 15 + partial * 5)

    # ── 2. History category affinity (25 pts) ──────────────────────────────
    if past_events:
        category_counts = {}
        past_tags = set()
        for pe in past_events:
            if pe.category:
                category_counts[pe.category] = category_counts.get(pe.category, 0) + 1
            past_tags.update(parse_tags(pe.mood_tags))

        # Category match
        if event.category in category_counts:
            freq = min(category_counts[event.category], 5)
            score += freq * 3  # up to 15 pts

        # Past mood tag overlap
        if event_tags & past_tags:
            score += min(10, len(event_tags & past_tags) * 5)

    # ── 3. Location proximity (20 pts) ─────────────────────────────────────
    if user_locations and event.lat and event.lng:
        distances = [
            haversine_km(event.lat, event.lng, lat, lng)
            for lat, lng in user_locations
        ]
        min_dist = min(distances)
        if min_dist < 5:
            score += 20
        elif min_dist < 15:
            score += 15
        elif min_dist < 30:
            score += 10
        elif min_dist < 60:
            score += 5

    # ── 4. Time-of-day affinity (10 pts) ───────────────────────────────────
    if user_hours and event.event_time:
        event_hour = event.event_time.hour
        close_hours = sum(1 for h in user_hours if abs(h - event_hour) <= 2)
        score += min(10, close_hours * 2)

    # ── 5. Recency of event creation (10 pts) ──────────────────────────────
    # Decays linearly over a 30-day window instead of a ~10-day cliff, so
    # "recency" behaves like a gradual signal rather than an on/off switch.
    RECENCY_WINDOW_DAYS = 30
    days_old = max(0, (datetime.now() - event.created_at).days)
    score += max(0.0, 10 * (1 - days_old / RECENCY_WINDOW_DAYS))

    return min(100.0, score)


def get_recommendations(user_id, limit=12, exclude_bookmarked=True):
    """
    Return up to `limit` recommended upcoming public events for the user,
    sorted by relevance score descending.
    """
    user = User.query.get(user_id)
    if not user:
        return []

    # Events already joined or bookmarked
    joined_ids = {
        p.event_id for p in Participation.query.filter_by(user_id=user_id).all()
    }
    if exclude_bookmarked:
        bookmarked_ids = {
            b.event_id for b in Bookmark.query.filter_by(user_id=user_id).all()
        }
        joined_ids.update(bookmarked_ids)

    now = datetime.now()

    # Candidate events. `.in_()` on an empty set correctly matches no rows,
    # so we always use a real SQLAlchemy expression here instead of the
    # Python literal `True`, which depended on engine-specific no-op
    # handling rather than well-defined query semantics.
    candidates = Event.query.filter(
        Event.is_public.is_(True),
        Event.is_cancelled.is_(False),
        Event.event_time > now,
        ~Event.id.in_(joined_ids)
    ).all()

    if not candidates:
        return []

    # Build user context
    user_interests = set(parse_tags(user.interests))

    past_events = db.session.query(Event).join(Participation).filter(
        Participation.user_id == user_id,
        Participation.status == 'approved',
        Event.event_time < now
    ).all()

    user_locations = [
        (e.lat, e.lng) for e in past_events if e.lat and e.lng
    ]

    user_hours = [
        e.event_time.hour for e in past_events if e.event_time
    ]

    # Score and sort
    scored = [
        (event, score_event(user, event, past_events, user_interests, user_locations, user_hours))
        for event in candidates
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [(event, score) for event, score in scored[:limit]]  # returns tuples


def get_mood_based_suggestions(user_id, limit=6, exclude_ids=None):
    """
    Return events matching user's interests/mood tags.
    Falls back to recent events if no interests set.

    `exclude_ids` lets callers keep this list disjoint from events the
    user has already joined/bookmarked, or from another recommendation
    list shown on the same page.
    """
    user = User.query.get(user_id)
    now = datetime.now()
    exclude_ids = set(exclude_ids) if exclude_ids else set()

    if not user or not user.interests:
        query = Event.query.filter(
            Event.is_public.is_(True),
            Event.is_cancelled.is_(False),
            Event.event_time > now
        )
        if exclude_ids:
            query = query.filter(~Event.id.in_(exclude_ids))
        return query.order_by(Event.created_at.desc()).limit(limit).all()

    user_interests = parse_tags(user.interests)
    seen = set(exclude_ids)
    results = []

    # Collect candidates per-interest, but don't break out of the whole
    # loop on the first interest that fills the quota — that made results
    # depend entirely on the arbitrary order of the user's interest tags.
    # Instead, gather a bounded number of candidates per tag and stop once
    # we have enough overall.
    for interest in user_interests:
        if len(results) >= limit:
            break

        events = Event.query.filter(
            Event.is_public.is_(True),
            Event.is_cancelled.is_(False),
            Event.event_time > now,
            db.or_(
                Event.category.ilike(f'%{interest}%'),
                Event.mood_tags.ilike(f'%{interest}%')
            )
        ).limit(limit).all()  # cap the per-tag query too

        for e in events:
            if e.id not in seen:
                seen.add(e.id)
                results.append(e)
                if len(results) >= limit:
                    break

    return results[:limit]


def get_trending_events(limit=12):
    """Return events with the most joins in the last 7 days."""
    now = datetime.now()
    week_ago = now - timedelta(days=7)

    # The join-count filter is applied in the ON clause (via the join
    # condition) rather than the WHERE clause, so events with zero recent
    # participations are still included with a count of 0, instead of
    # being silently dropped by an outerjoin-then-WHERE-filter pattern
    # (which behaves like an inner join).
    trending = db.session.query(
        Event,
        db.func.count(Participation.id).label('recent_joins')
    ).outerjoin(
        Participation,
        db.and_(
            Participation.event_id == Event.id,
            Participation.joined_at >= week_ago
        )
    ).filter(
        Event.is_public.is_(True),
        Event.is_cancelled.is_(False),
        Event.event_time > now
    ).group_by(Event.id).order_by(
        db.desc('recent_joins')
    ).limit(limit).all()

    return [event for event, _ in trending]