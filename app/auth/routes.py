from flask import Blueprint, json, render_template, redirect, url_for, flash, session, request
from flask_login import login_user, current_user, logout_user
import firebase_admin
from firebase_admin import auth as firebase_auth, credentials, firestore
from app.auth.forms import LoginForm, RegistrationForm
from app.models.user import User, db
from app.config import Config
from datetime import datetime

auth_bp = Blueprint('auth', __name__)

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
            user_record = auth.get_user_by_email(email)

            # Find user in the local database
            user = User.query.filter_by(email=email).first()
            if not user:
                # Create the user in the local database if not exists
                user = User(
                    id_=user_record.uid,
                    name=user_record.display_name or email.split('@')[0],
                    email=email,
                    profile_pic=user_record.photo_url or ""
                )
                db.session.add(user)
                db.session.commit()

                # Create or update user in Firestore
                firestore_db = firestore.client()
                firestore_db.collection('users').document(user_record.uid).set({
                    'name': user_record.display_name or email.split('@')[0],
                    'email': email,
                    'profile_pic': user_record.photo_url or "",
                    'created_at': datetime.now(),
                    'last_login': datetime.now(),
                    'auth_provider': 'email'
                })

            # Log in the user
            login_user(user)

            # Update last login time
            firestore_db = firestore.client()
            firestore_db.collection('users').document(user_record.uid).update({
                'last_login': datetime.now()
            })

            flash('Login successful!', 'success')
            # Redirect to profile page instead of dashboard
            return redirect(url_for('main.home()'))
        except Exception as e:
            flash(f'Login failed: {str(e)}', 'danger')

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

        # First check if a user with this email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            # Handle the case where the email already exists but with a different ID
            if existing_user.id != uid:
                # Link the accounts - update the existing user with the new UID
                existing_user.id = uid
                # Update other fields if needed
                existing_user.name = user_record.display_name
                existing_user.profile_pic = user_record.photo_url or ""
                db.session.commit()
                user = existing_user
            else:
                user = existing_user
        else:
        # Check if user exists in our database
            user = User.query.filter_by(id=uid).first()
            if not user:
                # Create a new user in database
                user = User(
                    id_=uid,
                    name=user_record.display_name,
                    email=user_record.email,
                    profile_pic=user_record.photo_url or ""
                )
                db.session.add(user)
                db.session.commit()

                # Create user in Firestore
                firestore_db = firestore.client()
                firestore_db.collection('users').document(uid).set({
                    'name': user_record.display_name,
                    'email': user_record.email,
                    'profile_pic': user_record.photo_url or "",
                    'created_at': datetime.now(),
                    'last_login': datetime.now(),
                    'auth_provider': 'google'
                })
            else:
                # Update last login time
                firestore_db = firestore.client()
                firestore_db.collection('users').document(uid).update({
                    'last_login': datetime.now()
                })

        # Log in the user
        login_user(user)

        return json.jsonify({'success': True}), 200

    except Exception as e:
        return json.jsonify({'error': str(e)}), 400

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    form = RegistrationForm()
    print("Form data: 1")
    if form.validate_on_submit():
        print("Form data: 2")  # Debugging line
        email = form.email.data
        password = form.password.data
        username = form.name.data if hasattr(form, 'name') else email.split('@')[0]

        try:
            # Create user in Firebase Auth
            user_record = firebase_auth.create_user(
                email=email,
                password=password,
                display_name=username
            )

            # Create user in database
            user = User(
                id_=user_record.uid,
                name=username,
                email=email,
                profile_pic=""
            )
            db.session.add(user)
            db.session.commit()

            # Create user in Firestore
            firestore_db = firestore.client()
            firestore_db.collection('users').document(user_record.uid).set({
                'name': username,
                'email': email,
                'profile_pic': "",
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