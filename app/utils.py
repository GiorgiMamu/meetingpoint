import html
import io
import math
import os
import time
import uuid
import logging
from datetime import timedelta

import bleach
import requests
from PIL import Image
from flask import current_app, url_for
from flask_mail import Message
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from geopy.geocoders import Nominatim
from itsdangerous import URLSafeTimedSerializer

from app import mail

# Initialize Cloudinary safely
try:
    import cloudinary
    import cloudinary.uploader

    cloudinary.config(
        cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
        api_key=os.environ.get('CLOUDINARY_API_KEY'),
        api_secret=os.environ.get('CLOUDINARY_API_SECRET')
    )
except ImportError:
    cloudinary = None

logger = logging.getLogger(__name__)


def sanitize(value):
    if value is None:
        return None
    cleaned = bleach.clean(str(value).strip(), tags=[], strip=True)
    return html.unescape(cleaned)


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
    sender = (
            current_app.config.get('MAIL_USERNAME')
            or current_app.config.get('MAIL_DEFAULT_SENDER')
    )

    if not sender:
        logging.getLogger(__name__).warning(
            f'Email not sent to {to}: no sender configured.'
        )
        return None

    msg = Message(
        subject=subject,
        sender=sender,
        recipients=[to],
        body=body
    )

    if not current_app.config.get('TESTING'):
        try:
            mail.send(msg)
        except Exception as e:
            logging.getLogger(__name__).error(f'Failed to send email to {to}: {e}')

    return msg

def send_verification_email(user):
    token = generate_token(user.email, salt='email-confirm')
    confirm_url = url_for('main.confirm_email', token=token, _external=True)
    body = f"""Hi {user.name},

Please confirm your email by clicking the link below:
{confirm_url}

This link expires in 1 hour.

If you did not register for MeetingPoint, ignore this email.
"""
    return send_email(user.email, 'MeetingPoint — Confirm your email', body)


def send_password_reset_email(user):
    from app import db
    token = generate_token(user.email, salt='password-reset')
    user.password_reset_token = token
    db.session.commit()
    reset_url = url_for('main.reset_password', token=token, _external=True)
    body = f"""Hi {user.name},

You requested a password reset. Click the link below:
{reset_url}

This link expires in 1 hour.

If you did not request a password reset, ignore this email.
"""
    return send_email(user.email, 'MeetingPoint — Password reset', body)


def save_event_photo(file):
    """Save and optimize an uploaded event photo. Supports Cloudinary and Local fallback."""
    # Defend against Python 3.14 gevent stream recursive lookups by reading into memory first
    try:
        file.seek(0)
        file_bytes = file.read()
        in_memory_file = io.BytesIO(file_bytes)
        in_memory_file_cloudinary = io.BytesIO(file_bytes)
    except Exception as e:
        logger.error(f"Failed reading image file buffer: {e}")
        return None

    # Fallback to local storage if Cloudinary variables are not configured
    if not os.environ.get('CLOUDINARY_CLOUD_NAME') or cloudinary is None:
        try:
            ext = file.filename.rsplit('.', 1)[-1].lower() if file.filename else 'jpg'
            filename = f"{uuid.uuid4().hex}.{ext}"
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, filename)

            img = Image.open(in_memory_file)
            img = img.convert('RGB')
            max_width = 1200
            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((max_width, new_height), Image.LANCZOS)

            img.save(filepath, optimize=True, quality=85)
            return filename
        except Exception as e:
            logger.error(f"Local event image optimization failed: {e}")
            return None

    try:
        # Pass pure memory stream cleanly to Cloudinary API wrapper
        upload_result = cloudinary.uploader.upload(
            in_memory_file_cloudinary,
            folder="meetingpoint_events"
        )
        return upload_result['secure_url']
    except Exception as e:
        logger.error(f"Cloudinary event upload failed: {e}")
        return None


def delete_event_photo(filename_or_url):
    """Delete an event photo from disk or Cloudinary."""
    if not filename_or_url:
        return

    if filename_or_url.startswith('http') and cloudinary is not None:
        try:
            public_id = "meetingpoint_events/" + filename_or_url.split('/')[-1].rsplit('.', 1)[0]
            cloudinary.uploader.destroy(public_id)
        except Exception as e:
            logger.error(f"Cloudinary deletion failed: {e}")
    else:
        filepath = os.path.join(current_app.root_path, 'static', 'uploads', filename_or_url)
        if os.path.exists(filepath):
            os.remove(filepath)


def send_cancellation_emails(event, participants):
    sent = []
    for participation in participants:
        user = participation.user
        body = f"""Hi {user.name},

Unfortunately, the event "{event.title}" scheduled for {(event.event_time + timedelta(hours=4)).strftime('%B %d, %Y at %H:%M')} has been cancelled by the host.

We're sorry for the inconvenience.

— MeetingPoint
"""
        sent.append(send_email(
            user.email,
            f'MeetingPoint — Event cancelled: {event.title}',
            body
        ))
    return sent


def geocode_location(location_text):
    if not location_text or not location_text.strip():
        return None, None
    try:
        geolocator = Nominatim(user_agent='meetingpoint_app')
        location = geolocator.geocode(location_text, timeout=5)
        if location:
            return location.latitude, location.longitude
        return None, None
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        logging.getLogger(__name__).warning(f'Geocoding failed for "{location_text}": {e}')
        return None, None


def haversine_distance(lat1, lng1, lat2, lng2):
    R = 6371  # Earth radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def filter_events_by_radius(events, center_lat, center_lng, radius_km):
    result = []
    for event in events:
        if event.lat is not None and event.lng is not None:
            dist = haversine_distance(center_lat, center_lng, event.lat, event.lng)
            if dist <= radius_km:
                result.append(event)
    return result


_exchange_cache = {'rates': {}, 'timestamp': 0}
_CACHE_TTL = 3600


def get_exchange_rates():
    now = time.time()
    if _exchange_cache['rates'] and (now - _exchange_cache['timestamp']) < _CACHE_TTL:
        return _exchange_cache['rates']

    fallback_rates = {
        'GEL': 1.0, 'USD': 2.75, 'EUR': 2.95, 'GBP': 3.45, 'TRY': 0.085, 'RUB': 0.030,
    }

    try:
        resp = requests.get(
            'https://api.frankfurter.app/latest',
            params={'base': 'GEL', 'symbols': 'USD,EUR,GBP,TRY,RUB'},
            timeout=3
        )
        if resp.status_code == 200:
            data = resp.json()
            rates = {'GEL': 1.0}
            for currency, rate in data.get('rates', {}).items():
                rates[currency] = round(1.0 / rate, 6)
            _exchange_cache['rates'] = rates
            _exchange_cache['timestamp'] = now
            return rates
    except Exception as e:
        logging.getLogger(__name__).warning(f'Exchange rate fetch failed: {e}')

    return fallback_rates


def convert_to_gel(amount, from_currency):
    if from_currency == 'GEL':
        return amount
    rates = get_exchange_rates()
    rate = rates.get(from_currency.upper(), 1.0)
    return amount * rate


def save_profile_photo(file):
    """Save and optimize a profile photo. Supports Cloudinary and Local fallback."""
    try:
        file.seek(0)
        file_bytes = file.read()
        in_memory_file = io.BytesIO(file_bytes)
        in_memory_file_cloudinary = io.BytesIO(file_bytes)
    except Exception as e:
        logger.error(f"Failed reading profile image file buffer: {e}")
        return None

    if not os.environ.get('CLOUDINARY_CLOUD_NAME') or cloudinary is None:
        try:
            ext = file.filename.rsplit('.', 1)[-1].lower() if file.filename else 'jpg'
            filename = f"profile_{uuid.uuid4().hex}.{ext}"
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, filename)

            img = Image.open(in_memory_file)
            img = img.convert('RGB')
            min_side = min(img.width, img.height)
            left = (img.width - min_side) // 2
            top = (img.height - min_side) // 2
            img = img.crop((left, top, left + min_side, top + min_side))
            img = img.resize((400, 400), Image.LANCZOS)
            img.save(filepath, optimize=True, quality=85)
            return filename
        except Exception as e:
            logger.error(f"Local profile image crop failed: {e}")
            return None

    try:
        upload_result = cloudinary.uploader.upload(
            in_memory_file_cloudinary,
            folder="meetingpoint_profiles"
        )
        return upload_result['secure_url']
    except Exception as e:
        logger.error(f"Cloudinary profile upload failed: {e}")
        return None