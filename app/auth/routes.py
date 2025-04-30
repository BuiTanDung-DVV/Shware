from flask import Blueprint, json, render_template, redirect, url_for, flash, session, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import login_user, current_user, logout_user
from flask_wtf.csrf import validate_csrf
import firebase_admin
from firebase_admin import auth as firebase_auth, credentials, firestore
from app.auth.forms import LoginForm, RegistrationForm
from app.models.user import User
from app.config import Config
from datetime import datetime
# from app import limiter

auth_bp = Blueprint('auth', __name__)

# --- Helper Function to get Default Profile Pic ---
_default_profile_pic_url = None

def get_default_profile_pic_url():
    global _default_profile_pic_url
    if _default_profile_pic_url is not None:
        return _default_profile_pic_url

    try:
        firestore_db = firestore.client()
        assets_ref = firestore_db.collection('assets')
        query = assets_ref.where('name', '==', 'profile pic').limit(1)
        docs = query.stream()
        for doc in docs:
            _default_profile_pic_url = doc.to_dict().get('value', "")
            return _default_profile_pic_url
        _default_profile_pic_url = ""
        return ""
    except Exception as e:
        print(f"Error fetching default profile pic URL: {e}")
        _default_profile_pic_url = ""
        return ""
# --- End Helper Function ---

# --Helper Function to Sync User Data--
def sync_user_to_firestore(uid, email, display_name, profile_pic_url, auth_provider):
    # First check existing data in Firestore
    firestore_db = firestore.client()
    user_doc_ref = firestore_db.collection('users').document(uid)
    user_doc = user_doc_ref.get()
    
    # Get existing role from Firestore or Firebase Auth
    if user_doc.exists:
        firestore_data = user_doc.to_dict()
        role = firestore_data.get('role', 'user')
    else:
        # If not in Firestore, check Firebase Auth
        try:
            user_record = firebase_auth.get_user(uid)
            role = user_record.custom_claims.get('role', 'user') if user_record.custom_claims else 'user'
        except:
            role = 'user'

    # Update Firestore
    if user_doc.exists:
        # Only update necessary fields for existing users
        update_data = {
            'last_login': datetime.now()
        }
        if user_doc.get('profile_pic') != profile_pic_url:
            update_data['profile_pic'] = profile_pic_url
        if user_doc.get('name') != display_name:
            update_data['name'] = display_name
        user_doc_ref.update(update_data)
    else:
        # Create new user document in Firestore
        user_doc_ref.set({
            'name': display_name,
            'email': email,
            'profile_pic': profile_pic_url,
            'created_at': datetime.now(),
            'last_login': datetime.now(),
            'auth_provider': auth_provider,
            'role': role
        })

    return User(id_=uid, name=display_name, email=email, profile_pic=profile_pic_url, role=role)

@auth_bp.route('/login', methods=['GET', 'POST'])
# @limiter.limit("5 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    form = LoginForm()
    if form.validate_on_submit():
        # Chuyển sang sử dụng client-side SDK trong login.html
        # Route này chỉ cần xử lý form hiển thị, còn xác thực sẽ qua /handle_firebase_auth
        flash('Please use the login form or Google login.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('login.html', form=form, config=Config)


@auth_bp.route('/handle_firebase_auth', methods=['POST'])
def handle_firebase_auth():
    try:
        # Kiểm tra CSRF token
        csrf_token = request.headers.get('X-CSRF-Token')
        validate_csrf(csrf_token)

        id_token = request.json.get('idToken')
        if not id_token:
            return json.jsonify({'error': 'No ID token provided'}), 400

        decoded_token = firebase_auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        user_record = firebase_auth.get_user(uid)
        email = user_record.email
        profile_pic_url = user_record.photo_url or get_default_profile_pic_url() or ""
        display_name = user_record.display_name or email.split('@')[0]
        auth_provider = decoded_token.get('firebase', {}).get('sign_in_provider', 'unknown')

        # Tái sử dụng logic xử lý người dùng
        user = sync_user_to_firestore(uid, email, display_name, profile_pic_url, auth_provider)
        login_user(user)

        return json.jsonify({'success': True}), 200

    except Exception as e:
        print(f"Handle Firebase Auth error: {e}")
        return json.jsonify({'error': 'Authentication failed.'}), 400

@auth_bp.route('/register', methods=['GET', 'POST'])
# @limiter.limit("3 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    form = RegistrationForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        username = form.name.data if hasattr(form, 'name') else email.split('@')[0]

        try:
            # Determine profile pic URL (will use default for registration)
            profile_pic_url = get_default_profile_pic_url() or ""

            # Create user in Firebase Auth
            user_record = firebase_auth.create_user(
                email=email,
                password=password,
                display_name=username,
                photo_url=profile_pic_url
            )

            # Create user in Firestore
            firestore_db = firestore.client()
            firestore_db.collection('users').document(user_record.uid).set({
                'name': username,
                'email': email,
                'profile_pic': profile_pic_url,
                'created_at': datetime.now(),
                'last_login': None,
                'auth_provider': 'email',
                'role': 'user'  # Set default role
            })

            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            flash(f'Registration failed: {str(e)}', 'danger')
            return redirect(url_for('auth.register'))

    return render_template('register.html', form=form)

@auth_bp.route('/logout')
def logout():
    logout_user()
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))

# Helper function to get user data from Firestore
def get_user_from_firestore(user_id):
    try:
        firestore_db = firestore.client()
        user_doc = firestore_db.collection('users').document(user_id).get()
        if user_doc.exists:
            return user_doc.to_dict()
        return None
    except Exception as e:
        print(f"Error retrieving user from Firestore: {e}")
        return None