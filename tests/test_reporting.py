import pytest
from datetime import datetime
from app import create_app, db
from app.models import User, Event, Report
from app.forms import ReportForm


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


def test_create_user_report(app, client):
    """Test creating a user report."""
    # Create users
    reporter = User(email="reporter@test.com", password_hash="hash", name="Reporter", is_active=True)
    reported_user = User(email="reported@test.com", password_hash="hash", name="Reported")
    db.session.add_all([reporter, reported_user])
    db.session.commit()

    # Create report
    report = Report(
        reporter_id=reporter.id,
        reported_user_id=reported_user.id,
        reason='harassment',
        description='This user is harassing me repeatedly'
    )
    db.session.add(report)
    db.session.commit()

    assert report.id is not None
    assert report.status == 'open'
    assert report.reason == 'harassment'


def test_create_event_report(app, client):
    """Test creating an event report."""
    # Create users and event
    reporter = User(email="reporter@test.com", password_hash="hash", name="Reporter")
    host = User(email="host@test.com", password_hash="hash", name="Host")
    db.session.add_all([reporter, host])
    db.session.commit()

    event = Event(
        host_id=host.id,
        title="Suspicious Event",
        event_time=datetime.now(),
        is_public=True
    )
    db.session.add(event)
    db.session.commit()

    report = Report(
        reporter_id=reporter.id,
        reported_event_id=event.id,
        reason='fraud',
        description='This looks like a scam event'
    )
    db.session.add(report)
    db.session.commit()

    assert report.reported_event_id == event.id
    assert report.reason == 'fraud'


def test_prevent_duplicate_reports(app):
    """Test that duplicate reports are prevented."""
    reporter = User(email="reporter@test.com", password_hash="hash", name="Reporter")
    reported_user = User(email="reported@test.com", password_hash="hash", name="Reported")
    db.session.add_all([reporter, reported_user])
    db.session.commit()

    # Create first report
    report1 = Report(
        reporter_id=reporter.id,
        reported_user_id=reported_user.id,
        reason='harassment',
        description='First report'
    )
    db.session.add(report1)
    db.session.commit()

    # Try to create duplicate
    report2 = Report(
        reporter_id=reporter.id,
        reported_user_id=reported_user.id,
        reason='spam',
        description='Second report'
    )
    db.session.add(report2)
    db.session.commit()

    # Query open reports for this user from this reporter
    open_report = Report.query.filter_by(
        reporter_id=reporter.id,
        reported_user_id=reported_user.id,
        status='open'
    ).first()

    assert open_report is not None
    assert open_report.id == report1.id


def test_update_report_status(app):
    """Test updating report status."""
    reporter = User(email="reporter@test.com", password_hash="hash", name="Reporter")
    reported_user = User(email="reported@test.com", password_hash="hash", name="Reported")
    admin = User(email="admin@test.com", password_hash="hash", name="Admin", role='admin')
    db.session.add_all([reporter, reported_user, admin])
    db.session.commit()

    report = Report(
        reporter_id=reporter.id,
        reported_user_id=reported_user.id,
        reason='harassment',
        description='Report'
    )
    db.session.add(report)
    db.session.commit()

    # Update status
    report.status = 'reviewed'
    report.reviewed_by_id = admin.id
    report.admin_notes = 'User warned'
    db.session.commit()

    updated = Report.query.get(report.id)
    assert updated.status == 'reviewed'
    assert updated.reviewed_by_id == admin.id
    assert updated.admin_notes == 'User warned'


def test_report_query_filtering(app):
    """Test filtering reports by status and type."""
    reporter = User(email="reporter@test.com", password_hash="hash", name="Reporter")
    user1 = User(email="user1@test.com", password_hash="hash", name="User 1")
    user2 = User(email="user2@test.com", password_hash="hash", name="User 2")
    host = User(email="host@test.com", password_hash="hash", name="Host")
    db.session.add_all([reporter, user1, user2, host])
    db.session.commit()

    event = Event(host_id=host.id, title="Event", event_time=datetime.now())
    db.session.add(event)
    db.session.commit()

    # Create reports
    report1 = Report(reporter_id=reporter.id, reported_user_id=user1.id, reason='spam', description='Spam')
    report2 = Report(reporter_id=reporter.id, reported_user_id=user2.id, reason='spam', description='Spam')
    report2.status = 'reviewed'
    report3 = Report(reporter_id=reporter.id, reported_event_id=event.id, reason='fraud', description='Fraud')
    db.session.add_all([report1, report2, report3])
    db.session.commit()

    # Query open user reports
    open_user_reports = Report.query.filter(
        Report.status == 'open',
        Report.reported_user_id.isnot(None)
    ).all()
    assert len(open_user_reports) == 1

    # Query event reports
    event_reports = Report.query.filter(Report.reported_event_id.isnot(None)).all()
    assert len(event_reports) == 1