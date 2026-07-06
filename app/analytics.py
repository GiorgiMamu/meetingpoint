"""
analytics.py - Event analytics and metrics calculation
Uses pandas, numpy, and matplotlib for data analysis and visualization
"""

import base64
import io
from datetime import datetime, timezone

import matplotlib
matplotlib.use('Agg')  # non-interactive backend, safe for background threads
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from app.models import Event, Participation, User
from app import db


def get_event_analytics(event_id):
    """
    Get comprehensive analytics for a specific event.
    Returns dict with attendance rate, charts, participant counts.
    """
    event = Event.query.get(event_id)
    if not event:
        return None

    participations = Participation.query.filter_by(event_id=event_id).all()

    total_participants = len(participations)
    approved_count = len([p for p in participations if p.status == 'approved'])
    pending_count = len([p for p in participations if p.status == 'pending'])
    declined_count = len([p for p in participations if p.status == 'declined'])

    attendance_rate = 0.0
    capacity_fill_rate = 0.0

    if event.capacity_max and event.capacity_max > 0:
        attendance_rate = (approved_count / event.capacity_max) * 100
        capacity_fill_rate = attendance_rate
    elif approved_count > 0:
        attendance_rate = 100.0
        capacity_fill_rate = 100.0

    df_participations = pd.DataFrame([
        {
            'user_id': p.user_id,
            'status': p.status,
            'joined_at': p.joined_at
        }
        for p in participations
    ])

    join_trend_chart = _generate_join_trend_chart(df_participations)
    capacity_chart = _generate_capacity_chart(event, approved_count)
    status_chart = _generate_status_distribution_chart(
        approved_count, pending_count, declined_count
    )

    return {
        'event_id': event_id,
        'event_title': event.title,
        'event_time': event.event_time.strftime('%B %d, %Y at %H:%M'),
        'total_participants': total_participants,
        'approved_count': approved_count,
        'pending_count': pending_count,
        'declined_count': declined_count,
        'attendance_rate': round(attendance_rate, 2),
        'capacity_fill_rate': round(capacity_fill_rate, 2),
        'capacity_max': event.capacity_max,
        'capacity_min': event.capacity_min,
        'join_trend_chart': join_trend_chart,
        'capacity_chart': capacity_chart,
        'status_chart': status_chart,
    }


def _generate_join_trend_chart(df):
    """Generate join trend over time as base64 image."""
    if df.empty or 'joined_at' not in df.columns or df['joined_at'].isna().all():
        return None

    try:
        df = df.copy()
        df['joined_at'] = pd.to_datetime(df['joined_at'])
        df['hour'] = df['joined_at'].dt.floor('h')  # lowercase 'h' for newer pandas
        hourly_joins = df.groupby('hour').size()

        fig, ax = plt.subplots(figsize=(10, 4))
        hourly_joins.plot(ax=ax, marker='o', color='#1F3D2B', linewidth=2)
        ax.set_title('Join trend over time', fontsize=12, fontweight='bold')
        ax.set_xlabel('Time', fontsize=10)
        ax.set_ylabel('Number of joins', fontsize=10)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()

        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format='png', dpi=80, bbox_inches='tight')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.read()).decode()
        plt.close(fig)

        return f"data:image/png;base64,{img_base64}"
    except Exception as e:
        plt.close('all')
        print(f"Error generating join trend chart: {e}")
        return None


def _generate_capacity_chart(event, approved_count):
    """Generate capacity utilization pie chart."""
    try:
        if not event.capacity_max or event.capacity_max <= 0:
            return None

        available = max(0, event.capacity_max - approved_count)

        if approved_count == 0 and available == 0:
            return None

        sizes = [approved_count, available]
        labels = [f'Filled ({approved_count})', f'Available ({available})']
        colors = ['#71bd84', '#e9ecef']

        fig, ax = plt.subplots(figsize=(5, 5))
        wedges, texts, autotexts = ax.pie(
            sizes,
            labels=None,
            colors=colors,
            autopct=lambda p: f'{p:.1f}%' if p > 3 else '',
            startangle=90,
            wedgeprops={'linewidth': 1, 'edgecolor': 'white'}
        )
        ax.legend(
            wedges, labels,
            loc='lower center',
            bbox_to_anchor=(0.5, -0.12),
            ncol=2,
            fontsize=9,
            frameon=False
        )
        ax.set_title(
            f'Capacity utilization (max: {event.capacity_max})',
            fontsize=11, fontweight='bold', pad=10
        )
        plt.tight_layout()

        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format='png', dpi=90, bbox_inches='tight')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.read()).decode()
        plt.close(fig)
        return f"data:image/png;base64,{img_base64}"
    except Exception as e:
        plt.close('all')
        print(f"Error generating capacity chart: {e}")
        return None


def _generate_status_distribution_chart(approved, pending, declined):
    """Generate participation status distribution pie chart."""
    try:
        total = approved + pending + declined
        if total == 0:
            return None

        data = [(approved, f'Approved ({approved})', '#1F3D2B'),
                (pending, f'Pending ({pending})', '#C2A97A'),
                (declined, f'Rejected ({declined})', '#A06A6A')]
        data = [(s, l, c) for s, l, c in data if s > 0]

        if not data:
            return None

        sizes = [d[0] for d in data]
        labels = [d[1] for d in data]
        colors = [d[2] for d in data]

        fig, ax = plt.subplots(figsize=(5, 5))
        wedges, texts, autotexts = ax.pie(
            sizes,
            labels=None,
            colors=colors,
            autopct=lambda p: f'{p:.1f}%' if p > 3 else '',
            startangle=90,
            wedgeprops={'linewidth': 1, 'edgecolor': 'white'}
        )
        ax.legend(
            wedges, labels,
            loc='lower center',
            bbox_to_anchor=(0.5, -0.12),
            ncol=2,
            fontsize=9,
            frameon=False
        )
        ax.set_title(
            'Participation status distribution',
            fontsize=11, fontweight='bold', pad=10
        )
        plt.tight_layout()

        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format='png', dpi=90, bbox_inches='tight')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.read()).decode()
        plt.close(fig)
        return f"data:image/png;base64,{img_base64}"
    except Exception as e:
        plt.close('all')
        print(f"Error generating status chart: {e}")
        return None




def get_host_dashboard_metrics(host_id):
    """Get aggregated metrics for host dashboard."""
    events = Event.query.filter_by(host_id=host_id).all()

    if not events:
        return {
            'total_events': 0,
            'total_participants': 0,
            'avg_attendance_rate': 0.0,
            'upcoming_count': 0,
            'top_events': [],
            'upcoming_events': [],
            'past_events': [],
        }

    now =  datetime.now(timezone.utc).replace(tzinfo=None)
    upcoming = [e for e in events if e.event_time >= now]
    past = [e for e in events if e.event_time < now]

    total_participations = Participation.query.filter(
        Participation.event_id.in_([e.id for e in events])
    ).count()

    event_analytics = []
    attendance_rates = []

    for event in events:
        analytics = get_event_analytics(event.id)
        if analytics:
            event_analytics.append(analytics)
            if analytics['attendance_rate'] > 0:
                attendance_rates.append(analytics['attendance_rate'])

    avg_attendance = np.mean(attendance_rates) if attendance_rates else 0.0
    top_events = sorted(
        event_analytics, key=lambda x: x['attendance_rate'], reverse=True
    )[:5]

    return {
        'total_events': len(events),
        'total_participants': total_participations,
        'avg_attendance_rate': round(avg_attendance, 2),
        'upcoming_count': len(upcoming),
        'top_events': top_events,
        'upcoming_events': upcoming[:5],
        'past_events': past[:5],
    }


def calculate_system_metrics():
    """Calculate system-wide metrics."""
    total_users = User.query.count()
    total_events = Event.query.count()
    total_participations = Participation.query.count()
    approved_count = Participation.query.filter_by(status='approved').count()
    avg_attendance = (
        (approved_count / total_participations * 100)
        if total_participations > 0 else 0
    )

    return {
        'total_users': total_users,
        'total_events': total_events,
        'total_participations': total_participations,
        'approved_participations': approved_count,
        'avg_attendance_rate': round(avg_attendance, 2),
    }