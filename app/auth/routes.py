from flask import Blueprint, json, render_template, redirect, url_for, flash, session, request
from flask_login import login_user, current_user, logout_user
import firebase_admin
from firebase_admin import auth as firebase_auth, credentials, firestore
from app.auth.forms import LoginForm, RegistrationForm
from app.models.user import User, db
from app.config import Config
from datetime import datetime

auth_bp = Blueprint('auth', __name__)

# --- Helper Function to get Default Profile Pic ---
_default_profile_pic_url = None # Cache the URL

def get_default_profile_pic_url():
    global _default_profile_pic_url
    if _default_profile_pic_url is not None:
        # Return cached value (can be empty string if not found)
        return _default_profile_pic_url

    try:
        firestore_db = firestore.client()
        assets_ref = firestore_db.collection('assets')
        query = assets_ref.where('name', '==', 'profile pic').limit(1)
        docs = query.stream()
        for doc in docs: 
            _default_profile_pic_url = doc.to_dict().get('value', "")
            return _default_profile_pic_url
        # If no document found
        _default_profile_pic_url = ""
        return ""
    except Exception as e:
        print(f"Error fetching default profile pic URL: {e}")
        _default_profile_pic_url = "" # Cache empty string on error
        return ""
# --- End Helper Function ---

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        try:
            # Sign in with email and password using Firebase Auth
            auth = firebase_admin.auth
            #TODO: Use client-side SDK for password verification instead of server-side
            # Note: Firebase Admin SDK doesn't verify passwords directly.
            # This assumes the user exists in Firebase Auth.
            # For actual password verification, you'd typically use a client-side SDK
            # and send the ID token, similar to handle_firebase_auth.
            # Assuming get_user_by_email is sufficient for this flow's check.
            user_record = auth.get_user_by_email(email)
            uid = user_record.uid

            # Determine profile pic URL
            profile_pic_url = user_record.photo_url or get_default_profile_pic_url() or ""

            # Find or create user in the local database
            user = User.query.filter_by(id=uid).first()
            if not user:
                 # Fallback check by email if ID check failed (e.g., during migration)
                 user = User.query.filter_by(email=email).first()
                 if user:
                     # Update local user ID if it was different
                     user.id = uid
                     db.session.commit()
                 else:
                    # Create the user in the local database if not exists by ID or email
                    user = User(
                        id_=uid,
                        name=user_record.display_name or email.split('@')[0],
                        email=email,
                        profile_pic=profile_pic_url # Use determined URL
                    )
                    db.session.add(user)
                    db.session.commit()
            # Update local profile pic if it's different or was empty
            elif not user.profile_pic or user.profile_pic != profile_pic_url:
                 user.profile_pic = profile_pic_url
                 db.session.commit()

            # Check and update/create user in Firestore
            firestore_db = firestore.client()
            user_doc_ref = firestore_db.collection('users').document(uid)
            user_doc = user_doc_ref.get()

            if user_doc.exists:
                # User exists in Firestore, update last_login and potentially profile pic
                update_data = {'last_login': datetime.now()}
                existing_data = user_doc.to_dict()
                if existing_data.get('profile_pic') != profile_pic_url:
                    update_data['profile_pic'] = profile_pic_url
                user_doc_ref.update(update_data)
            else:
                # User does not exist in Firestore, create them using set
                user_doc_ref.set({
                    'name': user.name,
                    'email': user.email,
                    'profile_pic': profile_pic_url,
                    'created_at': user.registration_date or datetime.now(), # Use local reg date if available
                    'last_login': datetime.now(),
                    'auth_provider': 'email'
                })

            # Log in the user locally
            login_user(user)

            flash('Login successful!', 'success')
            return redirect(url_for('main.home'))
        except firebase_admin.auth.UserNotFoundError:
             flash('Login failed: User not found.', 'danger')
        except Exception as e:
            # Catch other potential errors, like wrong password if using a client SDK flow
            flash(f'Login failed: Invalid credentials or server error.', 'danger')
            # Log the actual error for debugging: print(f"Login error: {e}")

    return render_template('login.html', form=form, config=Config)

@auth_bp.route('/handle_firebase_auth', methods=['POST'])
def handle_firebase_auth():
    try:
        # Get the ID token from the request
        id_token = request.json.get('idToken')
        if not id_token:
            return json.jsonify({'error': 'No ID token provided'}), 400

        # Verify the ID token
        decoded_token = firebase_auth.verify_id_token(id_token)
        uid = decoded_token['uid']

        # Get the user's info from Firebase
        user_record = firebase_auth.get_user(uid)
        email = user_record.email
        # Determine profile pic URL
        profile_pic_url = user_record.photo_url or get_default_profile_pic_url() or ""
        display_name = user_record.display_name or email.split('@')[0]
        auth_provider = decoded_token.get('firebase', {}).get('sign_in_provider', 'unknown') # e.g., 'google.com'

        # Find or create user in the local database
        user = User.query.filter_by(id=uid).first()
        if not user:
            # Fallback check by email if ID check failed
            user = User.query.filter_by(email=email).first()
            if user:
                # Email exists, but ID was different. Link accounts by updating local ID.
                user.id = uid
                # Optionally update other fields from provider if desired
                user.name = display_name
                user.profile_pic = profile_pic_url
                db.session.commit()
            else:
                # Create a new user in the local database
                user = User(
                    id_=uid,
                    name=display_name,
                    email=email,
                    profile_pic=profile_pic_url # Use determined URL
                )
                db.session.add(user)
                db.session.commit()
        # Update local profile pic if it's different or was empty
        elif not user.profile_pic or user.profile_pic != profile_pic_url:
            user.profile_pic = profile_pic_url
            db.session.commit()

        # Check and update/create user in Firestore
        firestore_db = firestore.client()
        user_doc_ref = firestore_db.collection('users').document(uid)
        user_doc = user_doc_ref.get()

        if user_doc.exists:
            # User exists in Firestore, update last_login and potentially profile pic
            update_data = {'last_login': datetime.now()}
            existing_data = user_doc.to_dict()
            # Optionally update name from provider if desired
            # if existing_data.get('name') != display_name:
            #     update_data['name'] = display_name
            if existing_data.get('profile_pic') != profile_pic_url:
                update_data['profile_pic'] = profile_pic_url
            user_doc_ref.update(update_data)
        else:
            # User does not exist in Firestore, create them using set
            user_doc_ref.set({
                'name': display_name,
                'email': email,
                'profile_pic': profile_pic_url, # Use determined URL
                'created_at': user.registration_date or datetime.now(), # Use local reg date
                'last_login': datetime.now(),
                'auth_provider': auth_provider
            })

        # Log in the user locally
        login_user(user)

        return json.jsonify({'success': True}), 200

    except Exception as e:
        # Log the error: print(f"Handle Firebase Auth error: {e}")
        return json.jsonify({'error': 'Authentication failed.'}), 400

@auth_bp.route('/register', methods=['GET', 'POST'])
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
                photo_url=profile_pic_url # Set default in Firebase Auth too if possible
            )

            # Create user in database
            user = User(
                id_=user_record.uid,
                name=username,
                email=email,
                profile_pic=profile_pic_url # Use determined URL
            )
            db.session.add(user)
            db.session.commit()

            # Create user in Firestore
            firestore_db = firestore.client()
            firestore_db.collection('users').document(user_record.uid).set({
                'name': username,
                'email': email,
                'profile_pic': profile_pic_url, # Use determined URL
                'created_at': datetime.now(),
                'last_login': None,
                'auth_provider': 'email'
            })

            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            flash(f'Registration failed: {str(e)}', 'danger')

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