"""
scheduler.py — Background task scheduler for MeetingPoint.
Handles event reminders sent 24 hours before event start.
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def start_scheduler(app):
    """Start the APScheduler background scheduler."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            func=lambda: send_reminders(app),
            trigger='interval',
            hours=1,
            id='event_reminders',
            replace_existing=True
        )
        scheduler.start()
        logger.info('Scheduler started.')
    except Exception as e:
        logger.warning(f'Scheduler could not start: {e}')


def send_reminders(app):
    """
    Check for events starting in ~24 hours and send reminder emails
    to all approved participants who haven't been reminded yet.
    """
    with app.app_context():
        from app.models import Event, Participation
        from app.utils import send_email

        now = datetime.utcnow()
        window_start = now + timedelta(hours=23)
        window_end = now + timedelta(hours=25)

        upcoming = Event.query.filter(
            Event.event_time >= window_start,
            Event.event_time <= window_end,
            Event.is_cancelled == False,
            Event.is_public == True
        ).all()

        for event in upcoming:
            approved = Participation.query.filter_by(
                event_id=event.id,
                status='approved'
            ).all()

            for p in approved:
                user = p.user
                try:
                    body = f"""Hi {user.name},

This is a reminder that the event "{event.title}" is happening tomorrow at {event.event_time.strftime('%H:%M')}.

{"📍 " + event.location_text if event.location_text else ""}

See you there!

— MeetingPoint
"""
                    send_email(
                        user.email,
                        f'MeetingPoint — Reminder: {event.title} is tomorrow',
                        body
                    )
                    logger.info(f'Reminder sent to {user.email} for event {event.id}')
                except Exception as e:
                    logger.warning(f'Failed to send reminder to {user.email}: {e}')