from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def active_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_active:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def not_blocked_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated and current_user.is_blocked:
            flash('This action is restricted because your account is currently blocked.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


def host_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from app.models import Event
        event_id = kwargs.get('event_id')
        if event_id is None:
            abort(403)
        event = Event.query.get_or_404(event_id)
        if event.host_id != current_user.id:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function