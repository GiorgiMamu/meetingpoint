# Event Recommendation Engine

This document explains how MeetingPoint's recommendation system works: what
signals it uses, how scoring is calculated, and how the three supporting
functions (`get_recommendations`, `get_mood_based_suggestions`,
`get_trending_events`) fit together on the **For You** page.

## Overview

The `/discover/recommended` page shows different content depending on
whether the visitor is logged in:

| User state | What they see |
|---|---|
| Logged in | A personalized "Recommended for you" feed (scored) + a "Based on your interests" row (unscored, mood-based) |
| Logged out | A "Trending now" feed based on recent join activity |

## Scoring model

Each candidate event is scored from **0–100** by `score_event()`, built from
five independent signals:

| Signal | Max points | What it measures |
|---|---|---|
| Interest / mood tag match | 35 | Overlap between the user's stated interests and the event's tags/category |
| History category affinity | 25 | How often the user has attended this category/these tags before |
| Location proximity | 20 | Distance from the event to places the user has attended events before |
| Time-of-day affinity | 10 | How close the event's start time is to hours the user typically attends |
| Recency | 10 | How recently the event was created (decays over a 30-day window) |

Scores are clamped to a maximum of 100.

### 1. Interest / mood tag match (35 pts)

- The user's `interests` field and the event's `mood_tags` + category are
  both parsed into lowercase tag sets.
- **Exact matches** (a user interest equal to an event tag) are worth 15
  points each.
- **Partial matches** (one tag is a substring of the other, excluding pairs
  already counted as exact) are worth 5 points each.
- The total is capped at 35.

### 2. History category affinity (25 pts)

- Looks at the user's approved past participations.
- **Category frequency**: up to 5 points per past event in the same
  category as the candidate, capped at 15 points (5 events × 3 pts).
- **Mood tag overlap**: up to 10 points if the candidate's mood tags overlap
  with tags from the user's past events.

### 3. Location proximity (20 pts)

Distance is calculated with the haversine formula between the event and
every location the user has previously attended, using the closest one:

| Distance | Points |
|---|---|
| < 5 km | 20 |
| < 15 km | 15 |
| < 30 km | 10 |
| < 60 km | 5 |
| ≥ 60 km | 0 |

### 4. Time-of-day affinity (10 pts)

For each of the user's past event hours, if it falls within 2 hours of the
candidate event's start hour, it counts toward this score (2 points each,
capped at 10).

### 5. Recency (10 pts)

Newer events score higher, decaying linearly to 0 over a 30-day window:

```
points = max(0, 10 × (1 − days_since_created / 30))
```

An event created today scores close to 10; one created 30+ days ago scores 0.

## Supporting functions

### `get_recommendations(user_id, limit=12, exclude_bookmarked=True)`

The main scored feed.

1. Builds a set of event IDs the user has already joined (and optionally
   bookmarked) so they're excluded from candidates.
2. Pulls all upcoming, public, non-cancelled events not in that exclusion
   set.
3. Builds the user's context: interests, past attended locations, and past
   attended hours.
4. Scores every candidate with `score_event()` and returns the top `limit`,
   sorted descending, as `(event, score)` tuples.

### `get_mood_based_suggestions(user_id, limit=6, exclude_ids=None)`

A lighter-weight, unscored list shown in the "Based on your interests" row.

- If the user has no interests set, falls back to the most recently created
  upcoming events.
- Otherwise, iterates over the user's interest tags, gathering events whose
  category or mood tags match (via `ILIKE`), until `limit` results are
  collected.
- `exclude_ids` lets the caller keep this list disjoint from another list —
  in practice, the route passes in the IDs already shown in the main scored
  feed, and the function also excludes events the user has already joined
  or bookmarked.

### `get_trending_events(limit=12)`

Used for the logged-out "Trending now" view.

- Counts joins per event over the last 7 days.
- Includes events with **zero** recent joins (ranked at the bottom) rather
  than dropping them — the join window is applied as part of the join
  condition itself, not as a post-join filter, so it behaves as a true
  outer join.

## How the route assembles the page

`discover_recommended()`:

1. Logged-in users → calls `get_recommendations()` for the main feed, then
   `get_mood_based_suggestions()` with `exclude_ids` set to the main feed's
   event IDs, so the two sections never show duplicate events.
2. Logged-out users → calls `get_trending_events()` and wraps each result as
   `(event, 0)` so the template's `{% for event, score in events %}` loop
   works the same way for both authenticated and anonymous views.
3. Applies in-memory pagination (`per_page = 12`) over the already-scored,
   already-sorted list.

## Getting a near-100 score (for testing)

To produce a high-scoring test case, set up a user/event pair where:

1. **Interests** exactly match 3+ of the event's mood tags or category
   words (→ 35 pts, capped).
2. The user has **5+ approved past participations** in the same category,
   with overlapping mood tags (→ up to 25 pts).
3. The event's coordinates are **within 5 km** of a location from one of
   the user's past events (→ 20 pts).
4. The event's start hour is **within 2 hours** of 5+ of the user's past
   event hours (→ 10 pts).
5. The event's `created_at` is **right now** (→ ~10 pts).

Summing these hits the 100-point ceiling.