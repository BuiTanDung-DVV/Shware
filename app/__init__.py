from datetime import datetime
import firebase_admin
from firebase_admin import credentials
from flask import Flask
from app.config import Config
from dotenv import load_dotenv
from flask_login import LoginManager
from app.files_management.upload import format_filesize
from app.models import db
import pyrebase

load_dotenv('.env')
login_manager = LoginManager()

# Initialize Firebase Admin SDK (do this only once)
firebase_admin_initialized = False

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    app.jinja_env.filters['format_filesize'] = format_filesize
    
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

    # Jinja filter for converting timestamp to readable date
    @app.template_filter('timestamp_to_date')
    def timestamp_to_date_filter(s):
        if not s:
            return "N/A" # Handle cases where timestamp might be None
        try:
            # Assuming s is a Unix timestamp (seconds since epoch)
            return datetime.utcfromtimestamp(float(s)).strftime('%Y-%m-%d %H:%M:%S UTC')
        except (ValueError, TypeError):
            return "Invalid Date"

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

    from app.files_management.upload import upload_bp
    app.register_blueprint(upload_bp)

    from app.files_management.list_files import files_bp
    app.register_blueprint(files_bp)

    return app

@login_manager.user_loader
def load_user(user_id):
    from app.models.user import User
    return User.query.get(user_id)