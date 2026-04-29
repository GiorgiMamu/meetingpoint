from itsdangerous import URLSafeTimedSerializer
from flask import current_app, url_for
from flask_mail import Message
from app import mail
import bleach
import os
import uuid
from PIL import Image
from flask import current_app

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




def save_event_photo(file):
    """Save and optimize an uploaded event photo. Returns the filename."""
    ext = file.filename.rsplit('.', 1)[-1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
    os.makedirs(upload_folder, exist_ok=True)
    filepath = os.path.join(upload_folder, filename)

    img = Image.open(file)
    img = img.convert('RGB')

    # Resize to max 1200px width while keeping aspect ratio
    max_width = 1200
    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)

    img.save(filepath, optimize=True, quality=85)
    return filename


def delete_event_photo(filename):
    """Delete an event photo from disk."""
    if not filename:
        return
    filepath = os.path.join(current_app.root_path, 'static', 'uploads', filename)
    if os.path.exists(filepath):
        os.remove(filepath)


def send_cancellation_emails(event, participants):
    """Send cancellation notification to all participants of an event."""
    for participation in participants:
        user = participation.user
        body = f"""Hi {user.name},

Unfortunately, the event "{event.title}" scheduled for {event.event_time.strftime('%B %d, %Y at %H:%M')} has been cancelled by the host.

We're sorry for the inconvenience.

— MeetingPoint
"""
        send_email(user.email, f'MeetingPoint — Event Cancelled: {event.title}', body)





