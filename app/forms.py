from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Regexp
from flask_wtf.file import FileField, FileAllowed
from wtforms import TextAreaField, DateTimeLocalField, FloatField, IntegerField, SelectField, BooleanField
from wtforms.validators import Optional, NumberRange
from app.models import User
import bleach


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
        Length(min=8, max=128)
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password')
    ])
    submit = SubmitField('Register')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data.lower()).first()
        if user:
            raise ValidationError('That email is already registered.')


class LoginForm(FlaskForm):
    email = SanitizedStringField('Email', validators=[
        DataRequired(),
        Email(),
        Length(max=150)
    ])
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(max=128)
    ])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')


class RequestPasswordResetForm(FlaskForm):
    email = SanitizedStringField('Email', validators=[
        DataRequired(),
        Email(),
        Length(max=150)
    ])
    submit = SubmitField('Request Password Reset')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data.lower()).first()
        if not user:
            raise ValidationError('No account found with that email.')


class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(min=8, max=128)
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password')
    ])
    submit = SubmitField('Reset Password')


class EventForm(FlaskForm):
    title = SanitizedStringField('Event Title', validators=[
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
    mood_tags = SanitizedStringField('Mood Tags (comma separated)', validators=[
        Optional(),
        Length(max=255)
    ])
    photo = FileField('Event Photo', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'webp'], 'Images only.')
    ])
    capacity_min = IntegerField('Minimum Capacity', validators=[
        Optional(),
        NumberRange(min=1, max=10000)
    ])
    capacity_max = IntegerField('Maximum Capacity', validators=[
        Optional(),
        NumberRange(min=1, max=10000)
    ])
    price = FloatField('Price (0 = free)', validators=[
        Optional(),
        NumberRange(min=0)
    ])
    is_public = BooleanField('Public Event', default=True)
    approval_mode = SelectField('Approval Mode', choices=[
        ('automatic', 'Automatic — anyone can join instantly'),
        ('manual', 'Manual — you approve each participant')
    ])
    participant_list_visible = BooleanField('Show participant list to others', default=True)
    submit = SubmitField('Save Event')

    def validate_capacity_max(self, field):
        if field.data and self.capacity_min.data:
            if field.data < self.capacity_min.data:
                raise ValidationError('Maximum capacity must be greater than minimum.')