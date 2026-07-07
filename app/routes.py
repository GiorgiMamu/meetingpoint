"""
routes.py — All HTTP route handlers for MeetingPoint.
Organized into sections: general, auth, events, profiles, pages.
"""
import logging
import math
import os
from datetime import timedelta
from app.analytics import get_event_analytics, get_host_dashboard_metrics
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, abort, current_app)
from flask_login import login_user, logout_user, login_required, current_user

from app import db, bcrypt, limiter, cache
from app.decorators import admin_required, host_required, active_required, not_blocked_required
from app.forms import (RegistrationForm, LoginForm, RequestPasswordResetForm,
                       ResetPasswordForm, EventForm, EditProfileForm, BCRYPT_PASSWORD_TOO_LONG_MESSAGE, ReportForm)
from app.models import User, Event, Participation, Notification, Bookmark, Follow, Message, AuditLog
from app.utils import (send_verification_email, send_password_reset_email,
                       verify_token, sanitize, save_event_photo,
                       delete_event_photo, send_cancellation_emails,
                       geocode_location, filter_events_by_radius, convert_to_gel)

from datetime import datetime, timezone

def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)

main = Blueprint('main', __name__)
logger = logging.getLogger(__name__)


def render_private_profile(user):
    """Show a friendly private-profile page."""
    return render_template('errors/profile_private.html', user=user), 403


def can_view_profile(user):
    """Return True if the current user can view the given profile."""
    if current_user.is_authenticated and current_user.id == user.id:
        return True
    if current_user.is_authenticated and current_user.is_admin():
        return True
    if user.is_admin():
        return False
    return user.is_profile_public


def visible_following(user):
    """Users this profile follows, excluding admin accounts."""
    return [
        row.followed for row in user.following.order_by(Follow.created_at.desc()).all()
        if not row.followed.is_admin()
    ]


def add_invited_participation(event, user):
    """Upgrade existing pending participation to approved for an invited user."""
    participation = Participation.query.filter_by(
        event_id=event.id,
        user_id=user.id
    ).first()
    if participation and participation.status == 'pending':
        participation.status = 'approved'
    return participation


def has_event_invitation(user_id, event_id):
    """Return True if the user has a pending invitation notification for the event."""
    return Notification.query.filter_by(
        user_id=user_id,
        type='invitation',
        related_event_id=event_id
    ).first() is not None


def clear_event_invitation(user_id, event_id):
    """Remove invitation notifications so the host can re-invite after the user leaves."""
    Notification.query.filter_by(
        user_id=user_id,
        type='invitation',
        related_event_id=event_id
    ).delete(synchronize_session=False)


# ============================================================
# GENERAL
# ============================================================

@main.route('/')
def index():
    """Home page."""
    return render_template('index.html')


# ============================================================
# AUTH
# ============================================================

@main.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def register():
    """Register a new user account. Sends email verification link."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        name = sanitize(form.name.data)
        email = sanitize(form.email.data).lower()
        try:
            hashed_pw = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        except ValueError as exc:
            logger.warning('Registration rejected password due to bcrypt constraints: %s', exc)
            msg = BCRYPT_PASSWORD_TOO_LONG_MESSAGE
            form.password.errors.append(msg)
            flash(msg, 'danger')
            return render_template('account/register.html', form=form)
        user = User(name=name, email=email,
                    password_hash=hashed_pw, is_active=False)
        db.session.add(user)
        db.session.commit()
        send_verification_email(user)
        logger.info(f'New registration: {user.email}')
        flash('Account created. Please check your email to confirm your address.', 'info')
        return redirect(url_for('main.login'))
    return render_template('account/register.html', form=form)


@main.route('/confirm/<token>')
@limiter.limit("10 per minute")
def confirm_email(token):
    """Confirm a user's email address via token link."""
    email = verify_token(token, salt='email-confirm')
    if not email:
        flash('The confirmation link is invalid or has expired.', 'danger')
        return redirect(url_for('main.login'))
    user = User.query.filter_by(email=email).first_or_404()
    if user.is_active:
        flash('Account already confirmed.', 'info')
    else:
        user.is_active = True
        db.session.commit()
        logger.info(f'Email confirmed: {user.email}')
        flash('Email confirmed! You can now log in.', 'success')
    return redirect(url_for('main.login'))


@main.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    """Log in an existing user."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(
            email=sanitize(form.email.data).lower()).first()
        try:
            password_ok = bool(
                user and bcrypt.check_password_hash(user.password_hash, form.password.data)
            )
        except ValueError as exc:
            logger.warning('Login rejected password due to bcrypt constraints: %s', exc)
            form.password.errors.append(BCRYPT_PASSWORD_TOO_LONG_MESSAGE)
            return render_template('account/login.html', form=form)

        if password_ok:
            if not user.is_active:
                flash('Please confirm your email before logging in.', 'warning')
                return redirect(url_for('main.login'))
            login_user(user, remember=form.remember.data)
            logger.info(f'Login: {user.email}')

            # Log successful login
            from app.models import AuditLog
            audit_log = AuditLog(
                user_id=user.id,
                action='login_success',
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string[:255] if request.user_agent else None,
            )
            db.session.add(audit_log)
            db.session.commit()

            from urllib.parse import urlparse

            next_page = request.args.get('next')
            if next_page and urlparse(next_page).netloc != '':
                next_page = None
            return redirect(next_page or url_for('main.index'))
        else:
            # Log failed login attempt
            from app.models import AuditLog
            audit_log = AuditLog(
                action='login_failed',
                details=f'Email: {form.email.data}',
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string[:255] if request.user_agent else None,
            )
            db.session.add(audit_log)
            db.session.commit()

            logger.warning(f'Failed login attempt for: {form.email.data}')
            flash('Invalid email or password.', 'danger')

    return render_template('account/login.html', form=form)


@main.route('/logout')
@limiter.limit("10 per minute")
@login_required
def logout():
    """Log out the current user."""
    logger.info(f'Logout: {current_user.email}')
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.index'))


@main.route('/reset-password', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def request_password_reset():
    """Request a password reset email."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = RequestPasswordResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(
            email=sanitize(form.email.data).lower()).first()
        if user:
            send_password_reset_email(user)
            logger.info(f'Password reset requested: {user.email}')
        flash('If the given email is registered, you will receive a password reset link.', 'info')
        return redirect(url_for('main.login'))
    return render_template('account/request_reset.html', form=form)


@main.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def reset_password(token):
    """Reset a user's password via token link."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    email = verify_token(token, salt='password-reset')
    if not email:
        flash('The reset link is invalid or has expired.', 'danger')
        return redirect(url_for('main.request_password_reset'))
    user = User.query.filter_by(email=sanitize(email)).first_or_404()

    # Check token has not already been used
    if user.password_reset_token != token:
        flash('This reset link has already been used or is invalid.', 'danger')
        return redirect(url_for('main.request_password_reset'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        # Check new password is not same as current
        if bcrypt.check_password_hash(user.password_hash, form.password.data):
            flash('New password cannot be the same as your current password.', 'danger')
            return render_template('account/reset_password.html', form=form)
        try:
            user.password_hash = bcrypt.generate_password_hash(
                form.password.data).decode('utf-8')
        except ValueError as exc:
            logger.warning('Password reset rejected password due to bcrypt constraints: %s', exc)
            msg = BCRYPT_PASSWORD_TOO_LONG_MESSAGE
            form.password.errors.append(msg)
            flash(msg, 'danger')
            return render_template('account/reset_password.html', form=form)
        user.password_reset_token = None  # invalidate token after use
        db.session.commit()
        logger.info(f'Password reset completed: {user.email}')
        flash('Password updated. You can now log in.', 'success')
        return redirect(url_for('main.login'))
    return render_template('account/reset_password.html', form=form)


# ============================================================
# EVENTS — CRUD
# ============================================================

@main.route('/events/create', methods=['GET', 'POST'])
@login_required
@active_required
@not_blocked_required
@limiter.limit("10 per minute")
def create_event():
    """Create a new event. Host only."""
    form = EventForm()
    if form.validate_on_submit():
        # Auto-geocode if lat/lng not manually provided
        lat = form.lat.data
        lng = form.lng.data
        if not lat or not lng:
            if form.location_text.data:
                lat, lng = geocode_location(form.location_text.data)
                if lat and lng:
                    logger.info(f'Geocoded "{form.location_text.data}" -> ({lat}, {lng})')
                else:
                    logger.warning(f'Geocoding fallback: no coords for "{form.location_text.data}"')
        photo_filename = None
        if form.photo.data:
            photo_filename = save_event_photo(form.photo.data)

        event = Event(
            host_id=current_user.id,
            title=sanitize(form.title.data),
            description=sanitize(form.description.data),
            event_time=form.event_time.data + timedelta(minutes=form.tz_offset_minutes.data or 0),            location_text=sanitize(form.location_text.data),
            lat=lat,
            lng=lng,
            category=form.category.data,
            mood_tags=sanitize(form.mood_tags.data),
            photo=photo_filename,
            capacity_min=form.capacity_min.data,
            capacity_max=form.capacity_max.data,
            price=form.price.data or 0.0,
            currency=form.currency.data,
            is_public=form.is_public.data,
            is_anonymous=form.is_anonymous.data if current_user.is_admin() else False,
            approval_mode=form.approval_mode.data,
            participant_list_visible=form.participant_list_visible.data
        )
        db.session.add(event)
        db.session.commit()
        logger.info(f'Event created: {event.id} by user {current_user.id}')
        flash('Event created successfully!', 'success')
        return redirect(url_for('main.event_detail', event_id=event.id))
    return render_template('events/create_event.html', form=form, title='Host an event')


@main.route('/events/<int:event_id>')
def event_detail(event_id):
    """View a single event's detail page."""
    event = Event.query.get_or_404(event_id)
    user_participation = None
    if current_user.is_authenticated:
        user_participation = Participation.query.filter_by(
            user_id=current_user.id,
            event_id=event_id
        ).first()

    can_view_private_event = (
        current_user.is_authenticated and (
            current_user.id == event.host_id or
            current_user.is_admin() or
            (user_participation is not None and user_participation.status == 'approved') or
            has_event_invitation(current_user.id, event_id)
        )
    )
    if not event.is_public and not can_view_private_event:
        abort(403)

    participants = []
    if event.participant_list_visible or (
            current_user.is_authenticated and
            current_user.id == event.host_id):
        participants = [p for p in event.participations
                        if p.status == 'approved']

    invited_follower_ids = set()
    if current_user.is_authenticated and current_user.id == event.host_id:
        follower_ids = [
            row.follower_id for row in event.host.followers.all()
        ]
        if follower_ids:
            invited_follower_ids = {
                n.user_id for n in Notification.query.filter(
                    Notification.user_id.in_(follower_ids),
                    Notification.type == 'invitation',
                    Notification.related_event_id == event_id
                ).all()
            }

    return render_template('events/event_details.html',
                           event=event,
                           participants=participants,
                           user_participation=user_participation,
                           invited_follower_ids=invited_follower_ids)


@main.route('/events/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
@active_required
@not_blocked_required
@host_required
def edit_event(event_id):
    """Edit an existing event. Host only."""
    event = Event.query.get_or_404(event_id)
    if event.is_cancelled:
        flash('Cancelled events cannot be edited.', 'danger')
        return redirect(url_for('main.my_events'))
    form = EventForm(obj=event)
    if form.validate_on_submit():
        lat = form.lat.data
        lng = form.lng.data
        if not lat or not lng:
            if form.location_text.data:
                lat, lng = geocode_location(form.location_text.data)

        event.lat = lat
        event.lng = lng
        if form.photo.data and hasattr(form.photo.data, 'filename') and form.photo.data.filename:
            delete_event_photo(event.photo)
            event.photo = save_event_photo(form.photo.data)

        event.title = sanitize(form.title.data)
        event.description = sanitize(form.description.data)
        event.event_time = form.event_time.data + timedelta(minutes=form.tz_offset_minutes.data or 0)
        event.location_text = sanitize(form.location_text.data)
        event.lat = form.lat.data
        event.lng = form.lng.data
        event.category = form.category.data
        event.mood_tags = sanitize(form.mood_tags.data)
        event.capacity_min = form.capacity_min.data
        event.capacity_max = form.capacity_max.data
        event.price = form.price.data or 0.0
        event.currency = form.currency.data
        event.is_public = form.is_public.data
        if current_user.is_admin():
            event.is_anonymous = form.is_anonymous.data
        event.approval_mode = form.approval_mode.data
        event.participant_list_visible = form.participant_list_visible.data

        db.session.commit()
        logger.info(f'Event edited: {event.id} by user {current_user.id}')
        flash('Event updated successfully!', 'success')
        return redirect(url_for('main.event_detail', event_id=event.id))
    elif request.method == 'GET':
        form.event_time.data = event.event_time
    return render_template('events/create_event.html', form=form,
                           title='Edit event', event=event)


@main.route('/events/<int:event_id>/delete', methods=['POST'])
@login_required
@active_required
def delete_event(event_id):
    """Delete an event and notify participants. Host or Admin."""
    event = Event.query.get_or_404(event_id)
    if event.host_id != current_user.id and not current_user.is_admin():
        abort(403)
    participants = Participation.query.filter_by(event_id=event_id).all()
    approved = [p for p in participants if p.status == 'approved']

    send_cancellation_emails(event, approved)
    delete_event_photo(event.photo)

    Participation.query.filter_by(event_id=event_id).delete()
    Bookmark.query.filter_by(event_id=event_id).delete()
    Notification.query.filter_by(related_event_id=event_id).delete()
    db.session.delete(event)
    db.session.commit()

    logger.info(f'Event deleted: {event_id} by user {current_user.id}')
    flash('Event deleted and participants notified.', 'info')
    return redirect(request.args.get('next') or request.referrer or url_for('main.my_events'))


@main.route('/events/<int:event_id>/cancel', methods=['POST'])
@login_required
@active_required
def cancel_event(event_id):
    """Cancel an event and notify participants."""
    event = Event.query.get_or_404(event_id)
    if event.host_id != current_user.id:
        abort(403)
    participants = Participation.query.filter_by(event_id=event_id).all()
    approved = [p for p in participants if p.status == 'approved']

    send_cancellation_emails(event, approved)
    for participation in approved:
        notification = Notification(
            user_id=participation.user_id,
            actor_user_id=current_user.id,
            type='cancellation',
            message=f'Event "{event.title}" has been cancelled by the host.',
            related_event_id=event_id
        )
        db.session.add(notification)
    event.is_cancelled = True
    db.session.commit()

    logger.info(f'Event cancelled: {event_id} by user {current_user.id}')
    flash('Event cancelled and participants notified.', 'info')
    return redirect(request.args.get('next') or request.referrer or url_for('main.my_events'))


# ============================================================
# EVENTS — DISCOVER, SEARCH, MY EVENTS
# ============================================================

@main.route('/discover')
@limiter.limit("60 per minute")
def discover():
    """
    Discover page with caching for identical search queries.
    Lists all public events with keyword, category,
    date, mood tag, group size, price and location radius filters.
    Logs all search queries and filter usage for analytics.
    """
    page = request.args.get('page', 1, type=int)
    keyword = sanitize(request.args.get('q', ''))
    category = request.args.get('category', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    mood = sanitize(request.args.get('mood', ''))
    size_min = request.args.get('size_min', '', type=str)
    size_max = request.args.get('size_max', '', type=str)
    price_max = request.args.get('price_max', '', type=str)
    price_currency = request.args.get('price_currency', 'GEL')
    free_only = request.args.get('free_only', '')
    radius_km = request.args.get('radius_km', '', type=str)
    center_lat = request.args.get('center_lat', '', type=str)
    center_lng = request.args.get('center_lng', '', type=str)
    filters_open = bool(request.args.get('filters_open'))
    map_open = bool(request.args.get('map_open'))

    # Log all search queries and filters for analytics/debugging
    active_filters = {k: v for k, v in {
        'keyword': keyword,
        'category': category,
        'date_from': date_from,
        'date_to': date_to,
        'mood': mood,
        'size_min': size_min,
        'size_max': size_max,
        'price_max': price_max,
        'free_only': free_only,
        'radius_km': radius_km
    }.items() if v}

    if active_filters:
        logger.info(f'Search query: {active_filters}')

    should_cache = not current_user.is_authenticated  # only cache for anonymous visitors

    cache_key = (
        f"discover:{keyword}:{category}:{date_from}:{date_to}:"
        f"{mood}:{size_min}:{size_max}:{price_max}:{free_only}:{page}"
    )

    cached = cache.get(cache_key) if should_cache else None
    if cached and not (radius_km and center_lat and center_lng):
        return cached

    query = Event.query.filter_by(is_public=True)

    if keyword:
        query = query.filter(
            db.or_(
                Event.title.ilike(f'%{keyword}%'),
                Event.description.ilike(f'%{keyword}%'),
                Event.mood_tags.ilike(f'%{keyword}%'),
                Event.location_text.ilike(f'%{keyword}%')
            )
        )

    if category:
        query = query.filter_by(category=category)

    if mood:
        query = query.filter(Event.mood_tags.ilike(f'%{mood}%'))

    if date_from:
        try:
            query = query.filter(
                Event.event_time >= datetime.strptime(date_from, '%Y-%m-%d')
            )
        except ValueError:
            pass

    if date_to:
        try:
            query = query.filter(
                Event.event_time <= datetime.strptime(date_to, '%Y-%m-%d')
            )
        except ValueError:
            pass

    if free_only:
        query = query.filter(
            db.or_(Event.price == 0.0, Event.price.is_(None))
        )
    elif price_max:
        try:
            price_max_float = float(price_max)
            price_max_gel = convert_to_gel(price_max_float, price_currency)
            query = query.filter(Event.price <= price_max_gel)
        except ValueError:
            pass

    if size_min:
        try:
            query = query.filter(Event.capacity_max >= int(size_min))
        except ValueError:
            pass

    if size_max:
        try:
            query = query.filter(Event.capacity_min <= int(size_max))
        except ValueError:
            pass

    query = query.order_by(Event.event_time.asc())
    all_events = query.all()

    # Location radius filter (post-query, needs lat/lng math)
    if radius_km and center_lat and center_lng:
        try:
            all_events = filter_events_by_radius(
                all_events,
                float(center_lat),
                float(center_lng),
                float(radius_km)
            )
            logger.info(
                f'Radius filter: {radius_km}km from '
                f'({center_lat},{center_lng}) -> {len(all_events)} results'
            )
        except ValueError:
            pass

    # Manual pagination after radius filter
    per_page = 12
    total = len(all_events)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_events = all_events[start:end]
    total_pages = math.ceil(total / per_page) if total > 0 else 1

    categories = [
        ('social', 'Social'),
        ('sports', 'Sports'),
        ('arts and culture', 'Arts & Culture'),
        ('music', 'Music'),
        ('food and drinks', 'Food & Drinks'),
        ('outdoors', 'Outdoors'),
        ('games', 'Games'),
        ('education', 'Education'),
        ('technology', 'Technology'),
        ('wellness and health', 'Wellness & Health'),
        ('travel', 'Travel'),
        ('other', 'Other')
    ]

    result = render_template(
        'events/discover.html',
        events=paginated_events,
        total=total,
        page=page,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
        prev_num=page - 1,
        next_num=page + 1,
        categories=categories,
        keyword=keyword,
        selected_category=category,
        date_from=date_from,
        date_to=date_to,
        mood=mood,
        size_min=size_min,
        size_max=size_max,
        price_max=price_max,
        price_currency=price_currency,
        free_only=free_only,
        radius_km=radius_km,
        center_lat=center_lat,
        center_lng=center_lng
        ,filters_open=filters_open, map_open=map_open
    )

    # Radius search is not cached because it depends on dynamic coordinates
    if should_cache and not (radius_km and center_lat and center_lng):
        cache.set(cache_key, result, timeout=60)

    return result

# ============================================================
# BOOKMARKS
# ============================================================

@main.route('/bookmarks')
@login_required
def bookmarks():
    """Show all events bookmarked by the current user."""
    user_bookmarks = Bookmark.query.filter_by(
        user_id=current_user.id
    ).order_by(Bookmark.created_at.desc()).all()
    return render_template('events/bookmarks.html', bookmarks=user_bookmarks)


@main.route('/events/<int:event_id>/bookmark', methods=['POST'])
@login_required
@active_required
@limiter.limit("30 per minute")
def toggle_bookmark(event_id):
    """Add or remove a bookmark for an event."""
    existing = Bookmark.query.filter_by(
        user_id=current_user.id,
        event_id=event_id
    ).first()

    if existing:
        db.session.delete(existing)
        db.session.commit()
        flash('Bookmark removed.', 'info')
        logger.info(f'Bookmark removed: user={current_user.id} event={event_id}')
    else:
        bookmark = Bookmark(user_id=current_user.id, event_id=event_id)
        db.session.add(bookmark)
        db.session.commit()
        flash('Event bookmarked', 'success')
        logger.info(f'Bookmark added: user={current_user.id} event={event_id}')

    return redirect(request.referrer or url_for('main.event_detail', event_id=event_id))


@main.route('/my-events')
@login_required
def my_events():
    """List all events hosted by the current user."""
    events = Event.query.filter_by(
        host_id=current_user.id
    ).order_by(Event.event_time.desc()).all()
    return render_template('events/my_events.html', events=events)


@main.route('/history')
@login_required
def history():
    """Show past and upcoming events the user has participated in."""
    now = now_utc()
    participations = Participation.query.filter_by(
        user_id=current_user.id,
        status='approved'
    ).all()

    upcoming = []
    past = []
    for p in participations:
        if p.event.event_time >= now:
            upcoming.append(p.event)
        else:
            past.append(p.event)

    upcoming.sort(key=lambda e: e.event_time)
    past.sort(key=lambda e: e.event_time, reverse=True)

    return render_template('events/history.html',
                           upcoming=upcoming, past=past)


# ============================================================
# PROFILES
# ============================================================

@main.route('/profile/<int:user_id>')
def profile(user_id):
    """View a user's public profile."""
    user = User.query.get_or_404(user_id)

    if not can_view_profile(user):
        return render_private_profile(user)

    can_see_anon = current_user.is_authenticated and (
            current_user.is_admin() or current_user.id == user_id
    )

    hosted_events_query = Event.query.filter_by(host_id=user_id, is_public=True)
    if not can_see_anon:
        hosted_events_query = hosted_events_query.filter_by(is_anonymous=False)

    hosted_events = hosted_events_query.order_by(Event.event_time.desc()).limit(5).all()

    history_events = []
    if user.is_history_public or (
            current_user.is_authenticated and
            current_user.id == user_id):
        participations = Participation.query.filter_by(
            user_id=user_id, status='approved'
        ).all()

        history_events = []
        for p in participations:
            if not p.event.is_anonymous or can_see_anon:
                history_events.append(p.event)

    return render_template('profiles/profile.html',
                           user=user,
                           hosted_events=hosted_events,
                           history_events=history_events,
                           followers_count=user.followers.count(),
                           following_count=len(visible_following(user)))


@main.route('/profile/<int:user_id>/followers')
def profile_followers(user_id):
    """View a user's followers."""
    user = User.query.get_or_404(user_id)

    if not can_view_profile(user):
        return render_private_profile(user)

    if user.is_admin():
        abort(404)

    follower_rows = user.followers.order_by(Follow.created_at.desc()).all()
    followers = [row.follower for row in follower_rows]
    return render_template(
        'profiles/followers.html',
        user=user,
        followers=followers,
        followers_count=len(followers)
    )


@main.route('/profile/<int:user_id>/following')
def profile_following(user_id):
    """View users this profile follows."""
    user = User.query.get_or_404(user_id)

    if not can_view_profile(user):
        return render_private_profile(user)

    if user.is_admin():
        abort(404)

    following = visible_following(user)
    return render_template(
        'profiles/following.html',
        user=user,
        following=following,
        following_count=len(following)
    )


@main.route('/profile/edit', methods=['GET', 'POST'])
@login_required
@active_required
def edit_profile():
    """Edit the current user's profile."""
    from app.utils import save_profile_photo
    form = EditProfileForm()
    if form.validate_on_submit():
        if form.profile_photo.data and hasattr(form.profile_photo.data, 'filename') and form.profile_photo.data.filename:
            # Delete old photo if exists
            if current_user.profile_photo:
                old_path = os.path.join(current_app.root_path, 'static', 'uploads', current_user.profile_photo)
                if os.path.exists(old_path):
                    os.remove(old_path)
            current_user.profile_photo = save_profile_photo(form.profile_photo.data)

        current_user.name = form.name.data
        current_user.bio = form.bio.data
        current_user.location = form.location.data
        current_user.interests = form.interests.data
        if not current_user.is_admin():
            current_user.is_profile_public = form.is_profile_public.data
            current_user.is_history_public = form.is_history_public.data
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('main.profile', user_id=current_user.id))
    elif request.method == 'GET':
        form.name.data = current_user.name
        form.bio.data = current_user.bio
        form.location.data = current_user.location
        form.interests.data = current_user.interests
        if not current_user.is_admin():
            form.is_profile_public.data = current_user.is_profile_public
            form.is_history_public.data = current_user.is_history_public
    return render_template('profiles/edit_profile.html', form=form, user=current_user)
# ============================================================
# STATIC PAGES
# ============================================================

@main.route('/privacy')
def privacy():
    """Privacy policy page."""
    return render_template('legal/privacy.html')


@main.route('/terms')
def terms():
    """Terms of service page."""
    return render_template('legal/terms.html')


# ============================================================
# ADMIN PANEL
# ============================================================

@main.route('/admin/users')
@login_required
@admin_required
def admin_users():
    """List all users for administration."""
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)


@main.route('/admin/events')
@login_required
@admin_required
def admin_events():
    """List all events for administration."""
    events = Event.query.order_by(Event.created_at.desc()).all()
    return render_template('admin/events.html', events=events)


@main.route('/admin/users/<int:user_id>/toggle_block', methods=['POST'])
@login_required
@admin_required
def toggle_block_user(user_id):
    """Block or unblock a user."""
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot block yourself.', 'danger')
        return redirect(url_for('main.admin_users'))

    user.is_blocked = not user.is_blocked
    db.session.commit()
    status = 'blocked' if user.is_blocked else 'unblocked'
    logger.info(f'User {user_id} {status} by admin {current_user.id}')
    flash(f'User {user.name} has been {status}.', 'success')
    return redirect(request.referrer or url_for('main.admin_users'))


@main.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    """Permanently delete a user account."""
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot delete yourself.', 'danger')
        return redirect(url_for('main.admin_users'))

    name = user.name

    from app.models import Report

    # These FKs have no cascade from User — detach them instead of
    # blocking the delete, so notification/report/audit history is preserved.
    Notification.query.filter_by(actor_user_id=user_id).update(
        {'actor_user_id': None}, synchronize_session=False
    )
    Report.query.filter_by(reporter_id=user_id).update(
        {'reporter_id': None}, synchronize_session=False
    )
    Report.query.filter_by(reported_user_id=user_id).update(
        {'reported_user_id': None}, synchronize_session=False
    )
    Report.query.filter_by(reviewed_by_id=user_id).update(
        {'reviewed_by_id': None}, synchronize_session=False
    )
    AuditLog.query.filter_by(user_id=user_id).update(
        {'user_id': None}, synchronize_session=False
    )

    # Everything else (events, participations, bookmarks, their own
    # notifications, messages, follows) is handled by the cascade='all,
    # delete-orphan' relationships already defined on User.
    db.session.delete(user)
    db.session.commit()

    logger.info(f'User {user_id} deleted by admin {current_user.id}')
    flash(f'User {name} has been permanently deleted.', 'success')
    return redirect(request.referrer or url_for('main.admin_users'))

# ============================================================
# ERROR HANDLERS
# ============================================================

@main.app_errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403


@main.app_errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404


@main.app_errorhandler(500)
def server_error(e):
    import traceback
    from app.models import AuditLog
    from flask import request
    from flask_login import current_user

    error_details = f"{str(e)}\n\nStack Trace:\n{traceback.format_exc()}"

    # Log to file
    logger.error(f'500 ERROR: {error_details}')

    # Log to database if possible
    try:
        audit_log = AuditLog(
            user_id=current_user.id if current_user.is_authenticated else None,
            action='error_500',
            details=error_details[:2000],  # Truncate for DB
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string[:255] if request.user_agent else None,
            status_code=500
        )
        db.session.add(audit_log)
        db.session.commit()
    except Exception as db_error:
        logger.warning(f'Failed to log 500 error to AuditLog: {db_error}')

    return render_template('errors/500.html'), 500


# ============================================================
# FOLLOW / UNFOLLOW
# ============================================================

@main.route('/users/<int:user_id>/follow', methods=['POST'])
@login_required
@active_required
def follow_user(user_id):
    """Follow or unfollow a user."""
    if current_user.is_admin():
        flash('Admin accounts cannot follow other users.', 'info')
        return redirect(request.referrer or url_for('main.index'))

    if user_id == current_user.id:
        flash('You cannot follow yourself.', 'danger')
        return redirect(url_for('main.profile', user_id=user_id))

    user = User.query.get_or_404(user_id)
    if user.is_admin():
        return render_private_profile(user)

    existing = Follow.query.filter_by(
        follower_id=current_user.id,
        followed_id=user_id
    ).first()

    if existing:
        db.session.delete(existing)
        db.session.commit()
        flash(f'You unfollowed {user.name}.', 'info')
        logger.info(f'Unfollow: {current_user.id} -> {user_id}')
    else:
        follow = Follow(follower_id=current_user.id, followed_id=user_id)
        db.session.add(follow)

        notification = Notification(
            user_id=user_id,
            actor_user_id=current_user.id,
            type='follow',
            message=f'{current_user.name} started following you.',
            related_event_id=None
        )
        db.session.add(notification)
        db.session.commit()
        flash(f'You are now following {user.name}.', 'success')
        logger.info(f'Follow: {current_user.id} -> {user_id}')

    return redirect(request.referrer or url_for('main.profile', user_id=user_id))


# ============================================================
# JOIN / LEAVE EVENT
# ============================================================

@main.route('/events/<int:event_id>/join', methods=['POST'])
@login_required
@active_required
@not_blocked_required
def join_event(event_id):
    """Join a public event."""
    event = Event.query.get_or_404(event_id)

    if current_user.is_admin() and event.host_id != current_user.id:
        flash('Admins have full visibility into events and don\'t need to join.', 'info')
        return redirect(url_for('main.event_detail', event_id=event_id))

    if event.is_cancelled:
        flash('This event has been cancelled.', 'danger')
        return redirect(url_for('main.event_detail', event_id=event_id))

    invited_to_private_event = (
            not event.is_public and
            has_event_invitation(current_user.id, event_id)
    )
    if not event.is_public and not invited_to_private_event:
        abort(403)

    if event.host_id == current_user.id:
        flash('You are the host of this event.', 'info')
        return redirect(url_for('main.event_detail', event_id=event_id))

    existing = Participation.query.filter_by(
        user_id=current_user.id, event_id=event_id
    ).first()

    if existing:
        flash('You have already joined or requested to join this event.', 'info')
        return redirect(url_for('main.event_detail', event_id=event_id))

    if event.capacity_max:
        approved_count = Participation.query.filter_by(
            event_id=event_id, status='approved'
        ).count()
        if approved_count >= event.capacity_max:
            flash('This event is full.', 'danger')
            return redirect(url_for('main.event_detail', event_id=event_id))

    if event.approval_mode == 'automatic' or invited_to_private_event:
        status = 'approved'
        flash('You have joined the event!', 'success')
        # notify host
        notification = Notification(
            user_id=event.host_id,
            actor_user_id=current_user.id,
            type='join',
            message=f'{current_user.name} joined your event "{event.title}".',
            related_event_id=event_id
        )
        db.session.add(notification)
        # send approval email
        from app.utils import send_email
        send_email(
            current_user.email,
            f'MeetingPoint — You joined: {event.title}',
            f'Hi {current_user.name},\n\nyou have successfully joined "{event.title}" on {(event.event_time+timedelta(hours=4)).strftime('%B %d, %Y at %H:%M')}.\n\n— MeetingPoint'
        )
    else:
        status = 'pending'
        flash('Your join request has been sent. The host will review it.', 'info')
        notification = Notification(
            user_id=event.host_id,
            actor_user_id=current_user.id,
            type='join_request',
            message=f'{current_user.name} joined your event "{event.title}".',
            related_event_id=event_id
        )
        db.session.add(notification)

    participation = Participation(
        user_id=current_user.id,
        event_id=event_id,
        status=status
    )
    db.session.add(participation)
    db.session.commit()
    logger.info(f'Join event: user={current_user.id} event={event_id} status={status}')
    return redirect(url_for('main.event_detail', event_id=event_id))


@main.route('/events/<int:event_id>/leave', methods=['POST'])
@login_required
def leave_event(event_id):
    """Leave an event."""
    participation = Participation.query.filter_by(
        user_id=current_user.id, event_id=event_id
    ).first_or_404()

    event = Event.query.get_or_404(event_id)
    db.session.delete(participation)
    clear_event_invitation(current_user.id, event_id)
    db.session.commit()

    notification = Notification(
        user_id=event.host_id,
        actor_user_id=current_user.id,
        type='leave',
        message=f'{current_user.name} left your event "{event.title}".',
        related_event_id=event_id
    )
    db.session.add(notification)
    db.session.commit()

    flash('You have left the event.', 'info')
    logger.info(f'Leave event: user={current_user.id} event={event_id}')
    return redirect(url_for('main.event_detail', event_id=event_id))


# ============================================================
# PARTICIPANT APPROVAL (HOST)
# ============================================================

@main.route('/events/<int:event_id>/approve/<int:user_id>', methods=['POST'])
@login_required
@host_required
def approve_participant(event_id, user_id):
    """Approve a participant's join request."""
    participation = Participation.query.filter_by(
        user_id=user_id, event_id=event_id
    ).first()
    if not participation:
        flash('That request no longer exists.', 'info')
        return redirect(request.referrer or url_for('main.event_chat', event_id=event_id))
    if participation.status != 'pending':
        flash('That request has already been handled.', 'info')
        return redirect(request.referrer or url_for('main.event_chat', event_id=event_id))

    event = Event.query.get_or_404(event_id)

    if event.is_cancelled:
        flash('Cannot approve participants for a cancelled event.', 'danger')
        return redirect(request.referrer or url_for('main.event_detail', event_id=event_id))

    if event.capacity_max:
        current_approved = Participation.query.filter_by(
            event_id=event_id, status='approved'
        ).count()
        if current_approved >= event.capacity_max:
            flash(f'Cannot approve — event is already at full capacity ({event.capacity_max}).', 'danger')
            return redirect(request.referrer or url_for('main.event_detail', event_id=event_id))

    participation.status = 'approved'

    notification = Notification(
        user_id=user_id,
        type='approval',
        message=f'Your request to join "{event.title}" has been approved!',
        related_event_id=event_id
    )
    db.session.add(notification)
    Notification.query.filter_by(
        user_id=current_user.id,
        type='join_request',
        related_event_id=event_id,
        actor_user_id=user_id,
        is_read=False
    ).update({'is_read': True}, synchronize_session=False)
    db.session.commit()

    from app.utils import send_email
    user = db.session.get(User, user_id)
    send_email(
        user.email,
        f'MeetingPoint — Request approved: {event.title}',
        f'Hi {user.name},\n\nYour request to join "{event.title}" has been approved!\n\nThe event is on {event.event_time.strftime("%B %d, %Y at %H:%M")}.\n\n— MeetingPoint'
    )

    logger.info(f'Participant approved: user={user_id} event={event_id}')
    flash('Participant approved.', 'success')
    return redirect(request.referrer or url_for('main.event_detail', event_id=event_id))


@main.route('/events/<int:event_id>/decline/<int:user_id>', methods=['POST'])
@login_required
@host_required
def decline_participant(event_id, user_id):
    """Decline a participant's join request."""
    participation = Participation.query.filter_by(
        user_id=user_id, event_id=event_id
    ).first()
    if not participation:
        flash('That request no longer exists.', 'info')
        return redirect(request.referrer or url_for('main.event_chat', event_id=event_id))
    if participation.status != 'pending':
        flash('That request has already been handled.', 'info')
        return redirect(request.referrer or url_for('main.event_chat', event_id=event_id))

    event = Event.query.get_or_404(event_id)
    participation.status = 'declined'

    notification = Notification(
        user_id=user_id,
        type='declined',
        message=f'Your request to join "{event.title}" was rejected.',
        related_event_id=event_id
    )
    db.session.add(notification)
    Notification.query.filter_by(
        user_id=current_user.id,
        type='join_request',
        related_event_id=event_id,
        actor_user_id=user_id,
        is_read=False
    ).update({'is_read': True}, synchronize_session=False)
    db.session.commit()

    logger.info(f'Participant rejected: user={user_id} event={event_id}')
    flash('Participant rejected.', 'info')
    return redirect(request.referrer or url_for('main.event_detail', event_id=event_id))


@main.route('/events/<int:event_id>/remove/<int:user_id>', methods=['POST'])
@login_required
@host_required
def remove_participant(event_id, user_id):
    """Remove an approved participant from an event."""
    participation = Participation.query.filter_by(
        user_id=user_id, event_id=event_id
    ).first_or_404()

    event = Event.query.get_or_404(event_id)
    db.session.delete(participation)

    notification = Notification(
        user_id=user_id,
        type='removed',
        message=f'You have been removed from "{event.title}" by the host.',
        related_event_id=event_id
    )
    db.session.add(notification)
    db.session.commit()

    logger.info(f'Participant removed: user={user_id} event={event_id}')
    flash('Participant removed.', 'info')
    return redirect(request.referrer or url_for('main.event_detail', event_id=event_id))


# ============================================================
# INVITATIONS
# ============================================================

@main.route('/events/<int:event_id>/invite/<int:user_id>', methods=['POST'])
@login_required
@host_required
def invite_user(event_id, user_id):
    """Invite a user to an event."""
    event = Event.query.get_or_404(event_id)
    user = User.query.get_or_404(user_id)

    existing = Notification.query.filter_by(
        user_id=user_id,
        type='invitation',
        related_event_id=event_id
    ).first()

    if existing:
        flash(f'{user.name} has already been invited.', 'info')
        return redirect(request.referrer or url_for('main.event_detail', event_id=event_id))

    add_invited_participation(event, user)
    notification = Notification(
        user_id=user_id,
        actor_user_id=current_user.id,
        type='invitation',
        message=f'You have been invited to "{event.title}" by {current_user.name}.',
        related_event_id=event_id
    )
    db.session.add(notification)
    db.session.commit()

    from app.utils import send_email
    event_url = url_for('main.event_detail', event_id=event_id, _external=True)
    send_email(
        user.email,
        f'MeetingPoint — You\'ve been invited to {event.title}',
        f'Hi {user.name},\n\n{current_user.name} has invited you to "{event.title}".\n\nView the event: {event_url}\n\n— MeetingPoint'
    )

    flash(f'{user.name} has been invited.', 'success')
    logger.info(f'Invitation sent: event={event_id} to user={user_id} by {current_user.id}')
    return redirect(request.referrer or url_for('main.event_detail', event_id=event_id))


# ============================================================
# EVENT SHARING
# ============================================================

@main.route('/events/<int:event_id>/share')
def share_event(event_id):
    """Generate a shareable link for a public event."""
    event = Event.query.get_or_404(event_id)
    if event.is_cancelled:
        abort(403)
    if not current_user.is_authenticated or current_user.id != event.host_id:
        abort(403)
    share_url = url_for('main.event_detail', event_id=event_id, _external=True)
    followers = []
    invited_follower_ids = set()
    if current_user.is_authenticated:
        followers = [
            row.follower for row in current_user.followers.order_by(Follow.created_at.desc()).all()
        ]
        if followers:
            follower_ids = [follower.id for follower in followers]
            invited_follower_ids = {
                row.user_id for row in Notification.query.filter(
                    Notification.user_id.in_(follower_ids),
                    Notification.type == 'invitation',
                    Notification.related_event_id == event_id
                ).all()
            }
    return redirect(url_for('main.event_detail', event_id=event_id))


@main.route('/events/<int:event_id>/share-to-follower/<int:follower_id>', methods=['POST'])
@login_required
@active_required
def share_event_to_follower(event_id, follower_id):
    """Send an event invitation notification to one of the host's followers."""
    event = Event.query.get_or_404(event_id)
    if event.is_cancelled:
        abort(403)
    if event.host_id != current_user.id:
        abort(403)

    follower = User.query.get_or_404(follower_id)
    is_follower = Follow.query.filter_by(
        follower_id=follower_id,
        followed_id=current_user.id
    ).first() is not None
    if not is_follower:
        abort(403)

    existing_participation = Participation.query.filter_by(
        user_id=follower_id,
        event_id=event_id,
        status='approved'
    ).first()
    if existing_participation:
        return redirect(url_for('main.event_detail', event_id=event_id))

    existing_notification = Notification.query.filter_by(
        user_id=follower_id,
        type='invitation',
        related_event_id=event_id,
        actor_user_id=current_user.id
    ).first()
    if existing_notification:
        return redirect(url_for('main.event_detail', event_id=event_id))

    add_invited_participation(event, follower)
    notification = Notification(
        user_id=follower_id,
        actor_user_id=current_user.id,
        type='invitation',
        message=f'{current_user.name} invited you to "{event.title}".',
        related_event_id=event_id
    )
    db.session.add(notification)
    db.session.commit()

    logger.info(f'Invitation sent: event={event_id} to user={follower_id} by {current_user.id}')
    return redirect(url_for('main.event_detail', event_id=event_id))



# ============================================================
# CHAT PAGE
# ============================================================

@main.route('/chats')
@login_required
def chats():
    """List all event chats the user is part of (as host or approved participant)."""
    hosted = Event.query.filter_by(
        host_id=current_user.id,
        is_cancelled=False
    ).all()

    participations = Participation.query.filter_by(
        user_id=current_user.id,
        status='approved'
    ).all()
    joined = [p.event for p in participations if not p.event.is_cancelled]

    all_events = list({e.id: e for e in hosted + joined}.values())
    all_events.sort(key=lambda e: e.event_time, reverse=True)

    return render_template('events/chats.html', events=all_events)


@main.route('/events/<int:event_id>/chat')
@login_required
def event_chat(event_id):
    """View the chat for a specific event."""
    event = Event.query.get_or_404(event_id)

    is_host = event.host_id == current_user.id
    is_participant = Participation.query.filter_by(
        user_id=current_user.id,
        event_id=event_id,
        status='approved'
    ).first() is not None

    if not (is_host or is_participant or current_user.is_admin()):
        flash('You must be an approved participant to access this chat.', 'danger')
        return redirect(url_for('main.event_detail', event_id=event_id))

    messages = Message.query.filter_by(event_id=event_id).order_by(
        Message.timestamp.asc()
    ).all()

    pending = []
    if is_host and event.approval_mode == 'manual':
        pending = Participation.query.filter_by(
            event_id=event_id, status='pending'
        ).all()

    approved_participants = Participation.query.filter_by(
        event_id=event_id, status='approved'
    ).all()

    return render_template('events/event_chat.html',
                           event=event,
                           messages=messages,
                           pending=pending,
                           approved_participants=approved_participants,
                           is_host=is_host)


# ============================================================
# NOTIFICATIONS
# ============================================================

@main.route('/notifications')
@login_required
def notifications():
    """Show all notifications for the current user."""
    user_notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()

    pending_join_requests = set()
    for notif in user_notifications:
        if notif.type == 'join_request' and notif.related_event_id and notif.actor_user_id:
            pending = Participation.query.filter_by(
                event_id=notif.related_event_id,
                user_id=notif.actor_user_id,
                status='pending'
            ).first()
            if pending:
                pending_join_requests.add((notif.related_event_id, notif.actor_user_id))

    return render_template(
        'notifications.html',
        notifications=user_notifications,
        pending_join_requests=pending_join_requests
    )


@main.route('/notifications/mark-read', methods=['POST'])
@login_required
def mark_notifications_read():
    """Mark all notifications as read."""
    Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).update({'is_read': True}, synchronize_session=False)
    db.session.commit()
    return redirect(url_for('main.notifications'))


@main.route('/notifications/clear', methods=['POST'])
@login_required
def clear_notifications():
    """Delete all notifications for the current user."""
    Notification.query.filter_by(user_id=current_user.id).delete(synchronize_session=False)
    db.session.commit()
    flash('All notifications cleared.', 'info')
    return redirect(url_for('main.notifications'))


# ============================================================
# REPORTING SYSTEM (USER-FACING)
# ============================================================

@main.route('/events/<int:event_id>/report', methods=['GET', 'POST'])
@login_required
@active_required
def report_event(event_id):
    """Report an inappropriate event."""
    event = Event.query.get_or_404(event_id)

    if current_user.id == event.host_id:
        flash('You cannot report your own event.', 'info')
        return redirect(url_for('main.event_detail', event_id=event_id))

    form = ReportForm()

    if form.validate_on_submit():
        from app.models import Report

        # Check for duplicate reports
        existing = Report.query.filter_by(
            reporter_id=current_user.id,
            reported_event_id=event_id
        ).first()

        if existing and existing.status == 'open':
            flash('You have already reported this event.', 'warning')
            return redirect(url_for('main.event_detail', event_id=event_id))

        report = Report(
            reporter_id=current_user.id,
            reported_event_id=event_id,
            reason=form.reason.data,
            description=sanitize(form.description.data)
        )
        db.session.add(report)
        db.session.commit()

        logger.info(f'Event reported: event_id={event_id} by user={current_user.id} reason={form.reason.data}')
        flash('Thank you for reporting this event. Our admins will review it soon.', 'success')
        return redirect(url_for('main.event_detail', event_id=event_id))

    return render_template('events/report_event.html', form=form, event=event, report_type='event')


@main.route('/users/<int:user_id>/report', methods=['GET', 'POST'])
@login_required
@active_required
def report_user(user_id):
    """Report a user for inappropriate behavior."""
    reported_user = User.query.get_or_404(user_id)

    if current_user.id == user_id:
        flash('You cannot report yourself.', 'info')
        return redirect(url_for('main.profile', user_id=user_id))

    form = ReportForm()

    if form.validate_on_submit():
        from app.models import Report

        # Check for duplicate reports
        existing = Report.query.filter_by(
            reporter_id=current_user.id,
            reported_user_id=user_id
        ).first()

        if existing and existing.status == 'open':
            flash('You have already reported this user.', 'warning')
            return redirect(url_for('main.profile', user_id=user_id))

        report = Report(
            reporter_id=current_user.id,
            reported_user_id=user_id,
            reason=form.reason.data,
            description=sanitize(form.description.data)
        )
        db.session.add(report)
        db.session.commit()

        logger.info(f'User reported: user_id={user_id} by user={current_user.id} reason={form.reason.data}')
        flash('Thank you for reporting this user. Our admins will review them soon.', 'success')
        return redirect(url_for('main.profile', user_id=user_id))

    return render_template('events/report_event.html', form=form, user=reported_user, report_type='user')


# ============================================================
# HOST DASHBOARD & ANALYTICS
# ============================================================

@main.route('/dashboard')
@login_required
@active_required
def host_dashboard():
    """Host dashboard with aggregated metrics."""
    # Check if user has any events
    events = Event.query.filter_by(host_id=current_user.id).all()

    if not events:
        return render_template('dashboard/host_dashboard_empty.html', user=current_user)

    metrics = get_host_dashboard_metrics(current_user.id)

    return render_template('dashboard/host_dashboard.html',
                           metrics=metrics,
                           user=current_user)


@main.route('/dashboard/event/<int:event_id>')
@login_required
@active_required
@host_required
def event_dashboard(event_id):
    """Detailed analytics for a specific event."""
    event = Event.query.get_or_404(event_id)

    analytics = get_event_analytics(event_id)

    # Get pending participants for approval queue
    pending = Participation.query.filter_by(
        event_id=event_id,
        status='pending'
    ).all()

    # Get approved participants
    approved = Participation.query.filter_by(
        event_id=event_id,
        status='approved'
    ).all()

    return render_template('dashboard/event_analytics.html',
                           event=event,
                           analytics=analytics,
                           pending_participants=pending,
                           approved_participants=approved)


# ============================================================
# DISCOVER PAGE - RECOMMENDATIONS
# ============================================================

@main.route('/discover/recommended')
def discover_recommended():
    """
    Discover page with personalized recommendations.
    If user is logged in, show recommendations + mood-based suggestions (excluding hosted events).
    Otherwise show trending events.
    """
    page = request.args.get('page', 1, type=int)
    per_page = 12

    categories = [
        ('social', 'Social'),
        ('sports', 'Sports'),
        ('arts and culture', 'Arts & Culture'),
        ('music', 'Music'),
        ('food and drinks', 'Food & Drinks'),
        ('outdoors', 'Outdoors'),
        ('games', 'Games'),
        ('education', 'Education'),
        ('technology', 'Technology'),
        ('wellness and health', 'Wellness & Health'),
        ('travel', 'Travel'),
        ('other', 'Other'),
    ]
    category_labels = dict(categories)

    if current_user.is_authenticated and current_user.is_active:
        from app.recommendations import get_recommendations, get_mood_based_suggestions

        # Fetch basic list from engine
        raw_recommendations = get_recommendations(current_user.id, limit=per_page * 10)

        # 1. Filter out events where the user is the host
        recommendations = [
            (event, score) for event, score in raw_recommendations
            if event.host_id != current_user.id
        ]

        # Pass the main recommendation IDs in directly so mood suggestions
        rec_ids = {e.id for e, s in recommendations}
        raw_mood_suggestions = get_mood_based_suggestions(
            current_user.id, limit=6, exclude_ids=rec_ids
        )

        # 2. Filter out events where the user is the host from mood recommendations
        mood_suggestions = [
            event for event in raw_mood_suggestions
            if event.host_id != current_user.id
        ]
    else:
        from app.recommendations import get_trending_events

        recommendations = [
            (event, 0)
            for event in get_trending_events(limit=per_page * 10)
        ]
        mood_suggestions = []

    # Pagination
    total = len(recommendations)
    total_pages = math.ceil(total / per_page) if total > 0 else 1
    start = (page - 1) * per_page
    paginated = recommendations[start:start + per_page]

    return render_template(
        'events/discover_recommended.html',
        events=paginated,
        mood_suggestions=mood_suggestions,
        category_labels=category_labels,
        total=total,
        page=page,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
        prev_num=page - 1,
        next_num=page + 1,
    )
# ============================================================
# ADMIN PANEL - REPORTS
# ============================================================

@main.route('/admin/reports')
@login_required
@admin_required
def admin_reports():
    """View all reported content."""
    from app.models import Report

    status_filter = request.args.get('status', '')
    report_type = request.args.get('type', '')
    sort_by = request.args.get('sort', 'newest')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    query = Report.query

    # Apply filters
    if status_filter:
        query = query.filter_by(status=status_filter)

    if report_type == 'user':
        query = query.filter(Report.reported_user_id.isnot(None))
    elif report_type == 'event':
        query = query.filter(Report.reported_event_id.isnot(None))

    # Apply sorting
    if sort_by == 'oldest':
        query = query.order_by(Report.created_at.asc())
    else:  # newest
        query = query.order_by(Report.created_at.desc())

    # Pagination
    pagination = query.paginate(page=page, per_page=per_page)
    reports = pagination.items

    return render_template('admin/reports.html',
                           reports=reports,
                           status_filter=status_filter,
                           report_type=report_type,
                           sort_by=sort_by,
                           pagination=pagination)


@main.route('/admin/reports/<int:report_id>')
@login_required
@admin_required
def admin_report_detail(report_id):
    """View detailed report and take action."""
    from app.models import Report

    report = Report.query.get_or_404(report_id)

    return render_template('admin/report_detail.html', report=report)


@main.route('/admin/reports/<int:report_id>/update', methods=['POST'])
@login_required
@admin_required
def admin_update_report(report_id):
    """Update report status and notes."""
    from app.models import Report

    report = Report.query.get_or_404(report_id)

    new_status = sanitize(request.form.get('status', ''))
    admin_notes = sanitize(request.form.get('admin_notes', ''))
    if len(admin_notes) > 2000:
        admin_notes = admin_notes[:2000]

    if new_status in ['open', 'reviewed', 'resolved', 'dismissed']:
        report.status = new_status
        report.reviewed_at = now_utc()
        report.reviewed_by_id = current_user.id
        report.admin_notes = admin_notes
        db.session.commit()

        logger.info(f'Report updated: id={report_id} status={new_status} by admin={current_user.id}')
        flash('Report updated successfully.', 'success')

    return redirect(url_for('main.admin_report_detail', report_id=report_id))


# ============================================================
# ADMIN PANEL - SYSTEM LOGS
# ============================================================

@main.route('/admin/logs')
@login_required
@admin_required
def admin_logs():
    """View system audit logs."""
    from app.models import AuditLog

    action_filter = request.args.get('action', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    page = request.args.get('page', 1, type=int)
    per_page = 50

    query = AuditLog.query

    # Apply filters
    if action_filter:
        query = query.filter_by(action=action_filter)

    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(AuditLog.timestamp >= date_from_obj)
        except ValueError:
            pass

    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(AuditLog.timestamp < date_to_obj)
        except ValueError:
            pass

    # Sort by newest first
    query = query.order_by(AuditLog.timestamp.desc())

    # Pagination
    pagination = query.paginate(page=page, per_page=per_page)
    logs = pagination.items

    # Get unique actions for filter dropdown
    all_actions = db.session.query(AuditLog.action).distinct().all()
    actions_list = [a[0] for a in all_actions]

    return render_template('admin/logs.html',
                           logs=logs,
                           action_filter=action_filter,
                           date_from=date_from,
                           date_to=date_to,
                           pagination=pagination,
                           actions=actions_list)


@main.route('/admin/logs/<int:log_id>')
@login_required
@admin_required
def admin_log_detail(log_id):
    """View detailed log entry."""
    from app.models import AuditLog

    log = AuditLog.query.get_or_404(log_id)

    return render_template('admin/log_detail.html', log=log)


# ============================================================
# SETTINGS
# ============================================================

@main.route('/settings')
@login_required
@active_required
def settings():
    """Settings page."""
    from app.forms import ChangePasswordForm, ChangeEmailForm, DeleteAccountForm
    pw_form = ChangePasswordForm(prefix='pw')
    email_form = ChangeEmailForm(prefix='email')
    delete_form = DeleteAccountForm(prefix='delete')
    return render_template('settings.html',
                           pw_form=pw_form,
                           email_form=email_form,
                           delete_form=delete_form)


@main.route('/settings/change-password', methods=['POST'])
@login_required
@active_required
@limiter.limit("5 per minute")
def change_password():
    """Change password from settings page."""
    from app.forms import ChangePasswordForm, ChangeEmailForm, DeleteAccountForm
    pw_form = ChangePasswordForm(prefix='pw')
    email_form = ChangeEmailForm(prefix='email')
    delete_form = DeleteAccountForm(prefix='delete')

    if pw_form.validate_on_submit():
        if not bcrypt.check_password_hash(current_user.password_hash, pw_form.current_password.data):
            flash('Current password is incorrect.', 'danger')
            return render_template('settings.html', pw_form=pw_form,
                                   email_form=email_form, delete_form=delete_form)
        if bcrypt.check_password_hash(current_user.password_hash, pw_form.new_password.data):
            flash('New password cannot be the same as the current password.', 'danger')
            return render_template('settings.html', pw_form=pw_form,
                                   email_form=email_form, delete_form=delete_form)
        current_user.password_hash = bcrypt.generate_password_hash(
            pw_form.new_password.data).decode('utf-8')
        db.session.commit()
        logger.info(f'Password changed: {current_user.email}')
        flash('Password changed successfully.', 'success')
    return redirect(url_for('main.settings'))


@main.route('/settings/change-email', methods=['POST'])
@login_required
@active_required
@limiter.limit("3 per minute")
def change_email():
    """Change email address from settings page."""
    from app.forms import ChangePasswordForm, ChangeEmailForm, DeleteAccountForm
    pw_form = ChangePasswordForm(prefix='pw')
    email_form = ChangeEmailForm(prefix='email')
    delete_form = DeleteAccountForm(prefix='delete')

    if email_form.validate_on_submit():
        if not bcrypt.check_password_hash(current_user.password_hash, email_form.password.data):
            flash('Password is incorrect.', 'danger')
            return render_template('settings.html', pw_form=pw_form,
                                   email_form=email_form, delete_form=delete_form)
        new_email = email_form.new_email.data.lower()
        current_user.email = new_email
        current_user.is_active = False
        db.session.commit()
        send_verification_email(current_user)
        logger.info(f'Email change requested: {current_user.email}')
        logout_user()
        flash('Email updated. Please verify your new email address before logging in.', 'info')
        return redirect(url_for('main.login'))
    return redirect(url_for('main.settings'))


@main.route('/settings/delete-account', methods=['POST'])
@login_required
@limiter.limit("3 per hour")
def delete_account():
    """Permanently delete user account."""
    from app.forms import DeleteAccountForm
    delete_form = DeleteAccountForm(prefix='delete')
    if delete_form.validate_on_submit():
        if not bcrypt.check_password_hash(current_user.password_hash, delete_form.password.data):
            flash('Password is incorrect.', 'danger')
            return redirect(url_for('main.settings'))
        user = current_user._get_current_object()
        logout_user()
        db.session.delete(user)
        db.session.commit()
        logger.info(f'Account deleted: {user.email}')
        flash('Your account has been permanently deleted.', 'info')
        return redirect(url_for('main.index'))
    return redirect(url_for('main.settings'))