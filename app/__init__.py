import firebase_admin
from firebase_admin import credentials
from flask import Flask
from app.config import Config
from dotenv import load_dotenv
from flask_login import LoginManager
from app.models import db
import pyrebase

load_dotenv('.env')
login_manager = LoginManager()

# Initialize Firebase Admin SDK (do this only once)
firebase_admin_initialized = False

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # print("test")
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
    
    from app.dashboard.routes import dashboard_bp
    app.register_blueprint(dashboard_bp)
    
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