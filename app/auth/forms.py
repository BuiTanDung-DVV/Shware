from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, ValidationError
from wtforms.validators import DataRequired, Email, EqualTo, Length, Regexp, Optional

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

class ProfileUpdateForm(FlaskForm):
    display_name = StringField('Display Name', validators=[
        Optional(),
        Length(min=3, max=50, message='Display name must be between 3 and 50 characters')
    ])
    current_password = PasswordField('Current Password', validators=[Optional()])
    new_password = PasswordField('New Password', validators=[
        Optional(),
        Length(min=6, message='* New password must be at least 6 characters long'),
        EqualTo('confirm_new_password', message='New passwords must match')
    ])
    confirm_new_password = PasswordField('Confirm New Password', validators=[Optional()])
    submit = SubmitField('Update Profile')

    def validate(self, extra_validators=None):
        # Only require current password if new password is being set
        if self.new_password.data:
            if not self.current_password.data:
                self.current_password.errors.append('Current password is required to set a new password.')
                return False
            if not self.confirm_new_password.data:
                 self.confirm_new_password.errors.append('Please confirm your new password.')
                 return False
        return super(ProfileUpdateForm, self).validate(extra_validators=extra_validators)