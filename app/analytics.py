"""
analytics.py - Event analytics and metrics calculation
Uses pandas, numpy, and matplotlib for data analysis and visualization
"""

import base64
import io
import json
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from flask_login import current_user

from app import db
from app.models import Event, Participation, User


def get_event_analytics(event_id):
    """
    Get comprehensive analytics for a specific event.

    Returns dict with:
    - attendance_rate: float (0-100)
    - total_participants: int
    - capacity_fill_rate: float (0-100)
    - approval_stats: dict with pending/approved/declined counts
    - join_trend_chart: base64 image
    - capacity_usage_chart: base64 image
    - participation_status_chart: base64 image
    """
    event = Event.query.get(event_id)
    if not event:
        return None

    # Get all participations
    participations = Participation.query.filter_by(event_id=event_id).all()

    # Calculate basic metrics
    total_participants = len(participations)
    approved_count = len([p for p in participations if p.status == 'approved'])
    pending_count = len([p for p in participations if p.status == 'pending'])
    declined_count = len([p for p in participations if p.status == 'declined'])

    # Attendance rate (approved / capacity_max)
    attendance_rate = 0.0
    capacity_fill_rate = 0.0

    if event.capacity_max:
        attendance_rate = (approved_count / event.capacity_max) * 100
        capacity_fill_rate = (approved_count / event.capacity_max) * 100
    elif approved_count > 0:
        attendance_rate = 100.0
        capacity_fill_rate = 100.0

    # Create DataFrames for time-series analysis
    df_participations = pd.DataFrame([
        {
            'user_id': p.user_id,
            'status': p.status,
            'joined_at': p.joined_at
        }
        for p in participations
    ])

    # Generate charts
    join_trend_chart = _generate_join_trend_chart(df_participations)
    capacity_chart = _generate_capacity_chart(event, approved_count)
    status_chart = _generate_status_distribution_chart(approved_count, pending_count, declined_count)

    return {
        'event_id': event_id,
        'event_title': event.title,
        'total_participants': total_participants,
        'approved_count': approved_count,
        'pending_count': pending_count,
        'declined_count': declined_count,
        'attendance_rate': round(attendance_rate, 2),
        'capacity_fill_rate': round(capacity_fill_rate, 2),
        'capacity_max': event.capacity_max,
        'capacity_min': event.capacity_min,
        'approval_stats': {
            'approved': approved_count,
            'pending': pending_count,
            'declined': declined_count,
        },
        'join_trend_chart': join_trend_chart,
        'capacity_chart': capacity_chart,
        'status_chart': status_chart,
        'df_participations': df_participations,
        'event_time': event.event_time.strftime('%B %d, %Y at %H:%M'),

    }


def _generate_join_trend_chart(df):
    """Generate join trend over time as base64 image."""
    if df.empty or df['joined_at'].isna().all():
        return None

    try:
        # Convert to datetime if needed
        df['joined_at'] = pd.to_datetime(df['joined_at'])

        # Count joins by hour
        df['hour'] = df['joined_at'].dt.floor('H')
        hourly_joins = df.groupby('hour').size()

        # Create figure
        fig, ax = plt.subplots(figsize=(10, 4))
        hourly_joins.plot(ax=ax, marker='o', color='#007bff', linewidth=2)
        ax.set_title('Join Trend Over Time', fontsize=12, fontweight='bold')
        ax.set_xlabel('Time', fontsize=10)
        ax.set_ylabel('Number of Joins', fontsize=10)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()

        # Convert to base64
        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format='png', dpi=80, bbox_inches='tight')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.read()).decode()
        plt.close(fig)

        return f"data:image/png;base64,{img_base64}"
    except Exception as e:
        print(f"Error generating join trend chart: {e}")
        return None


def _generate_capacity_chart(event, approved_count):
    """Generate capacity utilization chart."""
    try:
        if not event.capacity_max:
            return None

        available = event.capacity_max - approved_count
        sizes = [approved_count, available]
        labels = [f'Filled\n({approved_count})', f'Available\n({available})']
        colors = ['#28a745', '#e9ecef']

        fig, ax = plt.subplots(figsize=(8, 6))
        wedges, texts, autotexts = ax.pie(
            sizes, labels=labels, colors=colors, autopct='%1.1f%%',
            startangle=90, textprops={'fontsize': 11}
        )
        ax.set_title(f'Capacity Utilization\n(Max: {event.capacity_max})',
                     fontsize=12, fontweight='bold')

        for autotext in autotexts:
            autotext.set_color('black')
            autotext.set_fontweight('bold')

        plt.tight_layout()

        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format='png', dpi=80, bbox_inches='tight')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.read()).decode()
        plt.close(fig)

        return f"data:image/png;base64,{img_base64}"
    except Exception as e:
        print(f"Error generating capacity chart: {e}")
        return None


def _generate_status_distribution_chart(approved, pending, declined):
    """Generate participation status distribution chart."""
    try:
        total = approved + pending + declined
        if total == 0:
            return None

        sizes = [approved, pending, declined]
        labels = [f'Approved\n({approved})', f'Pending\n({pending})', f'Declined\n({declined})']
        colors = ['#28a745', '#ffc107', '#dc3545']

        fig, ax = plt.subplots(figsize=(8, 6))
        wedges, texts, autotexts = ax.pie(
            sizes, labels=labels, colors=colors, autopct='%1.1f%%',
            startangle=90, textprops={'fontsize': 11}
        )
        ax.set_title('Participation Status Distribution', fontsize=12, fontweight='bold')

        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')

        plt.tight_layout()

        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format='png', dpi=80, bbox_inches='tight')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.read()).decode()
        plt.close(fig)

        return f"data:image/png;base64,{img_base64}"
    except Exception as e:
        print(f"Error generating status chart: {e}")
        return None


def get_host_dashboard_metrics(host_id):
    """
    Get aggregated metrics for host dashboard.

    Returns dict with:
    - total_events: int
    - total_participants: int
    - avg_attendance_rate: float
    - top_events: list of event analytics
    - upcoming_events: list
    - past_events: list
    """
    events = Event.query.filter_by(host_id=host_id).all()

    if not events:
        return {
            'total_events': 0,
            'total_participants': 0,
            'avg_attendance_rate': 0.0,
            'top_events': [],
            'upcoming_events': [],
            'past_events': [],
        }

    now = datetime.now()
    upcoming = []
    past = []

    for event in events:
        if event.event_time >= now:
            upcoming.append(event)
        else:
            past.append(event)

    # Calculate aggregate metrics
    total_participations = Participation.query.filter(
        Participation.event_id.in_([e.id for e in events])
    ).count()

    total_approved = Participation.query.filter(
        Participation.event_id.in_([e.id for e in events]),
        Participation.status == 'approved'
    ).count()

    # Get analytics for each event
    event_analytics = []
    attendance_rates = []

    for event in events:
        analytics = get_event_analytics(event.id)
        if analytics:
            event_analytics.append(analytics)
            if analytics['attendance_rate'] > 0:
                attendance_rates.append(analytics['attendance_rate'])

    avg_attendance = np.mean(attendance_rates) if attendance_rates else 0.0

    # Sort by attendance rate to get top events
    top_events = sorted(event_analytics, key=lambda x: x['attendance_rate'], reverse=True)[:5]

    return {
        'total_events': len(events),
        'total_participants': total_participations,
        'avg_attendance_rate': round(avg_attendance, 2),
        'upcoming_count': len(upcoming),
        'past_count': len(past),
        'top_events': top_events,
        'upcoming_events': upcoming[:5],
        'past_events': past[:5],
        'all_events_analytics': event_analytics,
    }


def calculate_system_metrics():
    """Calculate system-wide metrics."""
    total_users = User.query.count()
    total_events = Event.query.count()
    total_participations = Participation.query.count()

    approved_count = Participation.query.filter_by(status='approved').count()
    avg_attendance = (approved_count / total_participations * 100) if total_participations > 0 else 0

    return {
        'total_users': total_users,
        'total_events': total_events,
        'total_participations': total_participations,
        'approved_participations': approved_count,
        'avg_attendance_rate': round(avg_attendance, 2),
    }