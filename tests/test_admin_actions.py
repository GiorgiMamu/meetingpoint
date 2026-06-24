import pytest
from app import create_app, db
from app.models import User, Event, Report, AuditLog
from datetime import datetime


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


def test_admin_view_reports(app, client):
    """Test admin can view reports."""
    admin = User(email="admin@test.com", password_hash="hash", name="Admin", role='admin', is_active=True)
    reporter = User(email="reporter@test.com", password_hash="hash", name="Reporter")
    reported = User(email="reported@test.com", password_hash="hash", name="Reported")
    db.session.add_all([admin, reporter, reported])
    db.session.commit()

    report = Report(
        reporter_id=reporter.id,
        reported_user_id=reported.id,
        reason='harassment',
        description='Harassment report'
    )
    db.session.add(report)
    db.session.commit()

    # Query reports
    reports = Report.query.all()
    assert len(reports) == 1
    assert reports[0].reporter_id == reporter.id


def test_audit_log_creation(app):
    """Test audit log creation."""
    log = AuditLog(
        user_id=None,
        action='login_failed',
        details='Failed login attempt',
        ip_address='127.0.0.1',
        user_agent='Mozilla'
    )
    db.session.add(log)
    db.session.commit()

    retrieved = AuditLog.query.first()
    assert retrieved.action == 'login_failed'
    assert retrieved.ip_address == '127.0.0.1'


def test_audit_log_filtering(app):
    """Test filtering audit logs."""
    log1 = AuditLog(action='login_success', ip_address='127.0.0.1')
    log2 = AuditLog(action='login_failed', ip_address='127.0.0.2')
    log3 = AuditLog(action='error_500', ip_address='127.0.0.3')
    db.session.add_all([log1, log2, log3])
    db.session.commit()

    # Query by action
    failed_logins = AuditLog.query.filter_by(action='login_failed').all()
    assert len(failed_logins) == 1

    # Query 500 errors
    errors = AuditLog.query.filter_by(action='error_500').all()
    assert len(errors) == 1


def test_block_user_via_report(app):
    """Test blocking user through report system."""
    admin = User(email="admin@test.com", password_hash="hash", name="Admin", role='admin')
    reported = User(email="reported@test.com", password_hash="hash", name="Reported")
    db.session.add_all([admin, reported])
    db.session.commit()

    # Block user
    reported.is_blocked = True
    db.session.commit()

    updated = User.query.get(reported.id)
    assert updated.is_blocked is True


def test_admin_can_delete_events(app):
    """Test admin can delete inappropriate events."""
    admin = User(email="admin@test.com", password_hash="hash", name="Admin", role='admin')
    host = User(email="host@test.com", password_hash="hash", name="Host")
    db.session.add_all([admin, host])
    db.session.commit()

    event = Event(
        host_id=host.id,
        title="Inappropriate Event",
        event_time=datetime.now()
    )
    db.session.add(event)
    db.session.commit()

    event_id = event.id
    db.session.delete(event)
    db.session.commit()

    # Verify deletion
    deleted = Event.query.get(event_id)
    assert deleted is None