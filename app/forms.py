from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Regexp
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