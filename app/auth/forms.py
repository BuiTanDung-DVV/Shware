from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, ValidationError
from wtforms.validators import DataRequired, Email, EqualTo, Length, Regexp, Optional

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Mật khẩu', validators=[DataRequired()])
    submit = SubmitField('Đăng nhập')
    google_login = SubmitField('Đăng nhập với Google')
    
class RegistrationForm(FlaskForm):
    name = StringField('Tên tài khoản', validators=[
        DataRequired(), 
        Length(min=3, max=20, message='Tên tài khoản phải từ 3 đến 20 ký tự'),
        Regexp('^[A-Za-z0-9]+$', 
            message='* Tên tài khoản chỉ có thể chứa chữ cái và số')
    ])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Mật khẩu', validators=[
        DataRequired(), 
        EqualTo('confirm_password', message='Mật khẩu phải khớp'), 
        Length(min=6, message='* Mật khẩu phải từ 6 ký tự trở lên')
    ])
    confirm_password = PasswordField('Xác nhận mật khẩu', validators=[DataRequired()])
    submit = SubmitField('Đăng ký')
    
    def validate_name(self, name):
        # List of reserved usernames
        reserved = ['admin', 'administrator', 'moderator', 'mod', 'system', 
                    'support', 'staff', 'root', 'webmaster', 'security']
        if name.data.lower() in reserved:
            raise ValidationError('* Tên tài khoản này đã được sử dụng. Vui lòng chọn tên tài khoản khác.')

class ProfileUpdateForm(FlaskForm):
    display_name = StringField('Tên hiển thị', validators=[
        Optional(),
        Length(min=3, max=50, message='Tên hiển thị phải từ 3 đến 50 ký tự')
    ])
    current_password = PasswordField('Mật khẩu hiện tại', validators=[Optional()])
    new_password = PasswordField('Mật khẩu mới', validators=[
        Optional(),
        Length(min=6, message='* Mật khẩu mới phải từ 6 ký tự trở lên'),
        EqualTo('confirm_new_password', message='Mật khẩu mới phải khớp')
    ])
    confirm_new_password = PasswordField('Xác nhận mật khẩu mới', validators=[Optional()])
    submit = SubmitField('Cập nhật hồ sơ')

    def validate(self, extra_validators=None):
        # Only require current password if new password is being set
        if self.new_password.data:
            if not self.current_password.data:
                self.current_password.errors.append('Mật khẩu hiện tại là bắt buộc để đặt mật khẩu mới.')
                return False
            if not self.confirm_new_password.data:
                 self.confirm_new_password.errors.append('Vui lòng xác nhận mật khẩu mới.')
                 return False
        return super(ProfileUpdateForm, self).validate(extra_validators=extra_validators)