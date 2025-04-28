from datetime import datetime
import firebase_admin
from firebase_admin import credentials
from flask import Flask
from flask_wtf.csrf import CSRFProtect  # Add this import
from app.config import Config
from dotenv import load_dotenv
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.utils.date_formater import format_datetime_filter, timestamp_to_date
from app.utils.filesize_formater import format_filesize
from app.models import db
import pyrebase

load_dotenv('.env')
login_manager = LoginManager()
csrf = CSRFProtect()  # Initialize CSRF protection

# Initialize Firebase Admin SDK (do this only once)
firebase_admin_initialized = False

# Initialize limiter globally
#TODO: Uncomment and configure the limiter as needed
# limiter = Limiter(
#     key_func=get_remote_address,
#     default_limits=["200 per day", "50 per hour"],
#     storage_uri="memory://"
# )

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize CSRF protection
    csrf.init_app(app)
    
    # Initialize limiter with app
    # limiter.init_app(app)
    
    # Custom error handler for rate limiting
    # @app.errorhandler(429)
    # def ratelimit_handler(e):
    #     return {"error": f"Rate limit exceeded. {e.description}"}, 429
    
    
    app.jinja_env.filters['format_filesize'] = format_filesize
    app.jinja_env.filters['format_timestamp'] = timestamp_to_date
    app.jinja_env.filters['format_datetime'] = format_datetime_filter
    
    # Initialize SQLAlchemy
    db.init_app(app)
    
    # Initialize Firebase SDK
    firebase = pyrebase.initialize_app(app.config['FIREBASE_CONFIG'])
    app.firebase_auth = firebase.auth()
    app.db = firebase.database()
    
    # Initialize Firebase Admin SDK if not already initialized
    global firebase_admin_initialized
    if not firebase_admin_initialized:
        try:
            cred = credentials.Certificate(app.config['FIREBASE_ADMIN_SDK_PATH'])
            firebase_admin.initialize_app(cred)
            firebase_admin_initialized = True
        except ValueError:
            # App already initialized
            pass
        
    # Initialize Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    # Register blueprints
    from app.auth.routes import auth_bp
    app.register_blueprint(auth_bp)
    
    from app.user_profile.routes import user_profile_bp
    app.register_blueprint(user_profile_bp)
    
    from app.main.routes import main_bp
    app.register_blueprint(main_bp)

    from app.search.routes import search_bp
    app.register_blueprint(search_bp)
    from app.files_management.upload import upload_bp
    app.register_blueprint(upload_bp)

    from app.files_management.list_files import files_bp
    app.register_blueprint(files_bp)

    # Register admin blueprint
    from app.admin.routes import admin_bp
    app.register_blueprint(admin_bp)

    return app

@login_manager.user_loader
def load_user(user_id):
    from app.models.user import User
    return User.query.get(user_id)