from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Regexp
from flask_wtf.file import FileField, FileAllowed
from wtforms import TextAreaField, DateTimeLocalField, FloatField, IntegerField, SelectField, BooleanField
from wtforms.validators import Optional, NumberRange, ValidationError as WTFValidationError
from app.models import User
import bleach

# bcrypt only considers the first 72 bytes of the password. The underlying
# `bcrypt` package raises ValueError for longer passwords to avoid silent
# truncation, so we validate byte-length up-front.
BCRYPT_MAX_PASSWORD_BYTES = 72
# For UX we also cap passwords by characters; byte-length may still be lower
# for passwords containing emojis or some non-ASCII characters.
BCRYPT_MAX_PASSWORD_CHARS = 72

BCRYPT_PASSWORD_TOO_LONG_MESSAGE = (
    f'Password is too long.'
)

def bcrypt_max_bytes(max_bytes: int = BCRYPT_MAX_PASSWORD_BYTES, encoding: str = 'utf-8'):

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
    return bleach.clean(str(value).strip(), tags=[], strip=True)


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
    submit = SubmitField('Log In')


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
        ('arts', 'Arts & Culture'),
        ('music', 'Music'),
        ('food', 'Food & Drinks'),
        ('outdoors', 'Outdoors'),
        ('games', 'Games'),
        ('education', 'Education'),
        ('other', 'Other')
    ], validators=[DataRequired(message='Please select a category.')])
    mood_tags = SanitizedStringField('Mood tags (comma separated)', validators=[
        Optional(),
        Length(max=255)
    ])
    photo = FileField('Event Photo', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'webp'], 'Images only.')
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
    is_public = BooleanField('Public event', default=True)
    approval_mode = SelectField('Approval mode', choices=[
        ('automatic', 'Automatic — anyone can join instantly'),
        ('manual', 'Manual — you approve each participant')
    ])
    participant_list_visible = BooleanField('Show participant list to others', default=True)
    submit = SubmitField('Save Event')

    def validate_capacity_max(self, field):
        if field.data and self.capacity_min.data:
            if field.data < self.capacity_min.data:
                raise ValidationError('Maximum capacity must be greater than minimum.')

    def validate_lat(self, field):
        if field.data is not None:
            if field.data < -90 or field.data > 90:
                raise ValidationError('Latitude must be between -90 and 90.')

    def validate_lng(self, field):
        if field.data is not None:
            if field.data < -180 or field.data > 180:
                raise ValidationError('Longitude must be between -180 and 180.')