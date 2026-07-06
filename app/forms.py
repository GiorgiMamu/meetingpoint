import html

import bleach
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms import TextAreaField, DateTimeLocalField, FloatField, IntegerField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Regexp
from wtforms.validators import Optional, NumberRange

from app.models import User
from datetime import datetime, timezone, timedelta


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)

# bcrypt only considers the first 72 bytes of the password, the underlying
# `bcrypt` package raises ValueError for longer passwords to avoid silent
# truncation, so byte-length is validated up-front
BCRYPT_MAX_PASSWORD_BYTES = 72
# for UX passwords also capped by characters; byte-length may still be lower
# for passwords containing emojis or some non-ASCII characters
BCRYPT_MAX_PASSWORD_CHARS = 72


BCRYPT_PASSWORD_TOO_LONG_MESSAGE = 'Password is too long.'


def bcrypt_max_bytes(max_bytes: int = BCRYPT_MAX_PASSWORD_BYTES, encoding: str = 'utf-8'):
    # must pass 2 parameters
    def _validator(form, field):
        if not field.data:
            return
        try:
            size = len(str(field.data).encode(encoding))
        except Exception as exc:
            raise ValidationError('Invalid password encoding.') from exc

        if size > max_bytes:
            raise ValidationError(BCRYPT_PASSWORD_TOO_LONG_MESSAGE)

    return _validator


def _sanitize(value):
    if value is None:
        return value
    cleaned = bleach.clean(str(value).strip(), tags=[], strip=True)
    return html.unescape(cleaned)


class SanitizedStringField(StringField):
    def process_formdata(self, valuelist):
        super().process_formdata(valuelist)
        self.data = _sanitize(self.data)


class RegistrationForm(FlaskForm):
    name = SanitizedStringField('Name', validators=[
        DataRequired(),
        Length(min=2, max=100),
        Regexp(r'^[^<>{}()\[\]]*$', message='Name contains invalid characters.')
    ])
    email = SanitizedStringField('Email', validators=[
        DataRequired(),
        Email(),
        Length(max=150)
    ])
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters.'),
        Length(max=BCRYPT_MAX_PASSWORD_CHARS,
               message=f'Password is too long. Maximum is {BCRYPT_MAX_PASSWORD_CHARS} characters.'),
        bcrypt_max_bytes()
    ])
    confirm_password = PasswordField('Confirm password', validators=[
        DataRequired(),
        EqualTo('password'),
        Length(max=BCRYPT_MAX_PASSWORD_CHARS)
    ])
    submit = SubmitField('Register')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data.lower()).first()
        if user:
            raise ValidationError('This email is already registered.')


class LoginForm(FlaskForm):
    email = SanitizedStringField('Email', validators=[
        DataRequired(),
        Email(),
        Length(max=150)
    ])
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(max=BCRYPT_MAX_PASSWORD_CHARS,
               message=BCRYPT_PASSWORD_TOO_LONG_MESSAGE),
        bcrypt_max_bytes(),
    ])
    remember = BooleanField('Remember me')
    submit = SubmitField('Log in')


class RequestPasswordResetForm(FlaskForm):
    email = SanitizedStringField('Email', validators=[
        DataRequired(),
        Email(),
        Length(max=150)
    ])
    submit = SubmitField('Send password reset link')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data.lower()).first()
        if not user:
            raise ValidationError('No account found with the given email.')


class ResetPasswordForm(FlaskForm):
    password = PasswordField('New password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters.'),
        Length(max=BCRYPT_MAX_PASSWORD_CHARS,
               message=f'Password is too long. Maximum is {BCRYPT_MAX_PASSWORD_CHARS} characters.'),
        bcrypt_max_bytes()
    ])
    confirm_password = PasswordField('Confirm password', validators=[
        DataRequired(),
        EqualTo('password'),
        Length(max=BCRYPT_MAX_PASSWORD_CHARS)
    ])
    submit = SubmitField('Reset password')


class EventForm(FlaskForm):
    title = SanitizedStringField('Event title', validators=[
        DataRequired(),
        Length(min=3, max=150)
    ])
    description = TextAreaField('Description', validators=[
        Optional(),
        Length(max=3000)
    ])
    event_time = DateTimeLocalField('Date & Time', format='%Y-%m-%dT%H:%M',
                                    validators=[DataRequired()])
    tz_offset_minutes = IntegerField('Timezone offset', validators=[Optional()], default=0)
    location_text = SanitizedStringField('Location', validators=[
        Optional(),
        Length(max=255)
    ])
    lat = FloatField('Latitude', validators=[Optional()])
    lng = FloatField('Longitude', validators=[Optional()])
    category = SelectField('Category', choices=[
        ('', 'Select a category'),
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
    ], validators=[DataRequired(message='Please select a category.')])
    mood_tags = SanitizedStringField('Mood tags (comma separated)', validators=[
        Optional(),
        Length(max=255)
    ])
    photo = FileField('Event photo', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'webp'],
                    'Supported formats are only the following: jpg, jpeg, png and webp.')
    ])
    capacity_min = IntegerField('Minimum capacity', validators=[
        Optional(),
        NumberRange(min=1, max=10000)
    ])
    capacity_max = IntegerField('Maximum capacity', validators=[
        Optional(),
        NumberRange(min=1, max=10000)
    ])
    price = FloatField('Price (0 = free)', validators=[
        Optional(),
        NumberRange(min=0)
    ])
    currency = SelectField('Currency', choices=[
        ('GEL', 'GEL — Georgian Lari'),
        ('USD', 'USD — US Dollar'),
        ('EUR', 'EUR — Euro'),
        ('GBP', 'GBP — British Pound'),
        ('TRY', 'TRY — Turkish Lira'),
        ('RUB', 'RUB — Russian Ruble'),
    ])
    is_public = BooleanField('Public event', default=True)
    is_anonymous = BooleanField('Hide host identity', default=False)
    approval_mode = SelectField('Approval mode', choices=[
        ('automatic', 'Automatic — anyone can join instantly'),
        ('manual', 'Manual — you approve each participant')
    ])
    participant_list_visible = BooleanField('Show participant list to others', default=True)
    submit = SubmitField('Save event')

    def validate_capacity_max(self, field):
        if field.data and self.capacity_min.data:
            if field.data < self.capacity_min.data:
                raise ValidationError('Please enter a maximum greater than the minimum.')

    def validate_lat(self, field):
        if field.data is not None:
            if field.data < -90 or field.data > 90:
                raise ValidationError('Latitude must be between -90 and 90.')

    def validate_lng(self, field):
        if field.data is not None:
            if field.data < -180 or field.data > 180:
                raise ValidationError('Longitude must be between -180 and 180.')

    def validate_event_time(self, field):
        if field.data:
            offset = self.tz_offset_minutes.data or 0
            utc_value = field.data + timedelta(minutes=offset)
            now = now_utc()
            if utc_value <= now:
                raise ValidationError('Please choose a date and time in the future.')


class EditProfileForm(FlaskForm):
    name = SanitizedStringField('Name', validators=[
        DataRequired(),
        Length(min=2, max=100)
    ])
    bio = SanitizedStringField('Bio', validators=[
        Optional(),
        Length(max=500)
    ])
    location = SanitizedStringField('Location', validators=[
        Optional(),
        Length(max=150)
    ])
    interests = SanitizedStringField('Interests (comma separated)', validators=[
        Optional(),
        Length(max=255)
    ])
    is_profile_public = BooleanField('Public profile')
    is_history_public = BooleanField('Public history')
    submit = SubmitField('Save changes')


class ReportForm(FlaskForm):
    """Form for users to report events or other users."""
    reason = SelectField('Reason', choices=[
        ('spam', 'Spam or misleading'),
        ('inappropriate', 'Inappropriate content'),
        ('harassment', 'Harassment or abuse'),
        ('fraud', 'Fraud or scam'),
        ('dangerous', 'Dangerous activity'),
        ('other', 'Other reason'),
    ], validators=[DataRequired()])

    description = TextAreaField('Description', validators=[
        DataRequired(),
        Length(min=10, max=1000, message='Please provide at least 10 characters describing the issue.')
    ])

    submit = SubmitField('Submit report')


class AdminReportFilterForm(FlaskForm):
    """Form for filtering reports in admin panel."""

    status = SelectField('Status', choices=[
        ('', 'All statuses'),
        ('open', 'Open'),
        ('reviewed', 'Reviewed'),
        ('resolved', 'Resolved'),
        ('dismissed', 'Dismissed'),
    ], validators=[Optional()])

    report_type = SelectField('Type', choices=[
        ('', 'All types'),
        ('user', 'User report'),
        ('event', 'Event report'),
    ], validators=[Optional()])

    sort_by = SelectField('Sort by', choices=[
        ('newest', 'Newest first'),
        ('oldest', 'Oldest first'),
    ], validators=[Optional()])

    submit = SubmitField('Filter')
