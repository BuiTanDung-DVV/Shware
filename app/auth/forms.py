
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, ValidationError
from wtforms.validators import DataRequired, Email, EqualTo, Length, Regexp

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')
    google_login = SubmitField('Login with Google')
    
class RegistrationForm(FlaskForm):
    name = StringField('Username', validators=[
        DataRequired(), 
        Length(min=3, max=20, message='Username must be between 3 and 20 characters'),
        Regexp('^[A-Za-z0-9]+$', 
            message='* Username can only contain letters',)
    ])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[
        DataRequired(), 
        EqualTo('confirm_password', message='Passwords must match'), 
        Length(min=6, message='* Password must be at least 6 characters long')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired()])
    submit = SubmitField('Register')
    
    def validate_name(self, name):
        # List of reserved usernames
        reserved = ['admin', 'administrator', 'moderator', 'mod', 'system', 
                    'support', 'staff', 'root', 'webmaster', 'security']
        if name.data.lower() in reserved:
            raise ValidationError('* This username is reserved. Please choose a different one.')