from functools import wraps
from flask import redirect, url_for
from flask_login import current_user
from datetime import datetime

def premium_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        # Check if user has an active subscription
        if current_user.subscription_status != 'active':
            return redirect(url_for('payment.subscribe'))
            
        # Check if subscription has expired
        current_time = datetime.now(datetime.UTC)
        if current_user.subscription_end_date and current_user.subscription_end_date < current_time:
            current_user.subscription_status = 'expired'
            return redirect(url_for('payment.subscribe'))
            
        return f(*args, **kwargs)
    return decorated_function