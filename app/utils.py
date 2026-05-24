from itsdangerous import URLSafeTimedSerializer
from flask import current_app, url_for
from flask_mail import Message
from app import mail
import bleach

def sanitize(value):
    if value is None:
        return None
    return bleach.clean(str(value).strip(), tags=[], strip=True)

def generate_token(data, salt):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return s.dumps(data, salt=salt)


def verify_token(token, salt, max_age=3600):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        data = s.loads(token, salt=salt, max_age=max_age)
    except Exception:
        return None
    return data


def send_email(to, subject, body):
    if current_app.config.get('TESTING'):
        return
    sender = current_app.config.get('MAIL_USERNAME')  # fetch at call time, not config load time
    msg = Message(
        subject,
        sender=sender,
        recipients=[to],
        body=body
    )
    mail.send(msg)

def send_verification_email(user):
    token = generate_token(user.email, salt='email-confirm')
    confirm_url = url_for('main.confirm_email', token=token, _external=True)
    body = f"""Hi {user.name},

Please confirm your email by clicking the link below:
{confirm_url}

This link expires in 1 hour.

If you did not register for MeetingPoint, ignore this email.
"""
    send_email(user.email, 'MeetingPoint — Confirm Your Email', body)


def send_password_reset_email(user):
    token = generate_token(user.email, salt='password-reset')
    reset_url = url_for('main.reset_password', token=token, _external=True)
    body = f"""Hi {user.name},

You requested a password reset. Click the link below:
{reset_url}

This link expires in 1 hour.

If you did not request this, ignore this email.
"""
    send_email(user.email, 'MeetingPoint — Password Reset', body)





