from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db, bcrypt, limiter
from app.models import User
from app.forms import RegistrationForm, LoginForm, RequestPasswordResetForm, ResetPasswordForm
from app.decorators import admin_required, host_required

import logging
from app.utils import (send_verification_email, send_password_reset_email,
                       verify_token, generate_token, sanitize)

main = Blueprint('main', __name__)
logger = logging.getLogger(__name__)


@main.route('/')
def index():
    return render_template('index.html')


# --- REGISTRATION ---
@main.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        name = sanitize(form.name.data)
        email = sanitize(form.email.data).lower()
        hashed_pw = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(
            name=name,
            email=email,
            password_hash=hashed_pw,
            is_active=False
        )
        db.session.add(user)
        db.session.commit()
        send_verification_email(user)
        logger.info(f'New registration: {user.email}')
        flash('Account created. Please check your email to confirm your address.', 'info')
        return redirect(url_for('main.login'))
    return render_template('register.html', form=form)


# --- EMAIL CONFIRMATION ---
@main.route('/confirm/<token>')
@limiter.limit("10 per minute")
def confirm_email(token):
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


# --- LOGIN ---
@main.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=sanitize(form.email.data).lower()).first()
        if user and bcrypt.check_password_hash(user.password_hash, form.password.data):
            if not user.is_active:
                flash('Please confirm your email before logging in.', 'warning')
                return redirect(url_for('main.login'))
            login_user(user, remember=form.remember.data)
            logger.info(f'Login: {user.email}')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('main.index'))
        else:
            logger.warning(f'Failed login attempt for: {form.email.data}')
            flash('Invalid email or password.', 'danger')
    return render_template('login.html', form=form)


# --- LOGOUT ---
@main.route('/logout')
@limiter.limit("10 per minute")
@login_required
def logout():
    logger.info(f'Logout: {current_user.email}')
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.index'))


# --- REQUEST PASSWORD RESET ---
@main.route('/reset-password', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def request_password_reset():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = RequestPasswordResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=sanitize(form.email.data).lower()).first()
        if user:
            send_password_reset_email(user)
            logger.info(f'Password reset requested: {user.email}')
        flash('If that email exists, a reset link has been sent.', 'info')
        return redirect(url_for('main.login'))
    return render_template('request_reset.html', form=form)


# --- RESET PASSWORD ---
@main.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    email = verify_token(token, salt='password-reset')
    if not email:
        flash('The reset link is invalid or has expired.', 'danger')
        return redirect(url_for('main.request_password_reset'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=sanitize(email)).first_or_404()
        user.password_hash = bcrypt.generate_password_hash(
            form.password.data).decode('utf-8')
        db.session.commit()
        logger.info(f'Password reset completed: {user.email}')
        flash('Password updated. You can now log in.', 'success')
        return redirect(url_for('main.login'))
    return render_template('reset_password.html', form=form)


# --- STATIC PAGES ---
@main.route('/privacy')
@limiter.limit("10 per minute")
def privacy():
    return render_template('privacy.html')


@main.route('/terms')
@limiter.limit("10 per minute")
def terms():
    return render_template('terms.html')


# --- ERROR HANDLERS ---
@main.app_errorhandler(403)
@limiter.limit("10 per minute")
def forbidden(e):
    return render_template('errors/403.html'), 403


@main.app_errorhandler(404)
@limiter.limit("10 per minute")
def not_found(e):
    return render_template('errors/404.html'), 404


@main.app_errorhandler(500)
@limiter.limit("10 per minute")
def server_error(e):
    logger.error(f'Server error: {e}')
    return render_template('errors/500.html'), 500