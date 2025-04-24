from flask import render_template, session, redirect, url_for, flash, Blueprint, request
from firebase_admin import firestore, auth as firebase_auth
from flask_login import login_required, current_user
from ..auth.forms import ProfileUpdateForm
from .. import db 
from ..models.user import User

user_profile_bp = Blueprint('user_profile', __name__)
db_firestore = firestore.client()

@user_profile_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileUpdateForm()
    user_id = current_user.id
    has_password_provider = False # Flag to track if user uses email/password

    try:
        firebase_user = firebase_auth.get_user(user_id)
        registration_date = firebase_user.user_metadata.creation_timestamp / 1000 if firebase_user.user_metadata else None

        # Check if 'password' provider is linked
        for provider in firebase_user.provider_data:
            if provider.provider_id == 'password':
                has_password_provider = True
                break

    except firebase_auth.UserNotFoundError:
        flash("User not found in Firebase.", "danger")
        return redirect(url_for('main.home'))
    except Exception as e:
        flash(f"Error fetching user data: {e}", "danger")
        return redirect(url_for('main.home')) 
        
    if form.validate_on_submit():
        print('Form submitted and validated.')
        flash('Display name updated successfully01.', 'success00')

        display_name = form.display_name.data
        if display_name and display_name != (firebase_user.display_name or ''):
            try:
                # Update Firebase Auth
                firebase_auth.update_user(user_id, display_name=display_name)
                
                # Update local SQLAlchemy DB
                local_user = User.query.get(user_id)
                if local_user:
                    local_user.name = display_name
                    db.session.commit()

                # Update Firestore 'users' collection
                try:
                    db_firestore.collection('users').document(user_id).update({'name': display_name})
                except Exception as firestore_e:
                    # Log or flash a specific error for Firestore update failure
                    flash(f'Error updating Firestore profile name: {firestore_e}', 'warning') 
                    # Decide if this should prevent the success message below

                flash('Display name updated successfully.', 'success')
                firebase_user = firebase_auth.get_user(user_id) # Refresh user data
            except Exception as e:
                flash(f'Error updating display name: {e}', 'danger')

        # --- Update Password Logic (only if user has password provider and fields submitted) ---
        new_password = form.new_password.data
        # Only attempt password update if the user has a password provider
        # and the new_password field was actually filled out.
        if has_password_provider and new_password:
             # The form's validate method already checks if current_password is provided
             # when new_password is set.
            try:
                firebase_auth.update_user(user_id, password=new_password)
                flash('Password updated successfully. Consider logging out and back in.', 'success')
            except firebase_auth.FirebaseError as e:
                 flash(f'Error updating password: {e.code}', 'danger')
            except Exception as e:
                 flash(f'An unexpected error occurred while updating password: {e}', 'danger')
        elif not has_password_provider and new_password:
            flash('Password cannot be changed for accounts logged in via Google or other providers.', 'info')


        return redirect(url_for('user_profile.profile'))
    elif request.method == 'POST': 
        print("Form validation failed.")
        print("Errors:", form.errors)
        flash("Form validation failed. Please check the errors below.", "danger")

    # Pre-populate form for GET request
    if request.method == 'GET':
        form.display_name.data = firebase_user.display_name or ''

    user_info = {
        'email': firebase_user.email,
        'name': firebase_user.display_name,
        'avatar': firebase_user.photo_url or url_for('static', filename='images/default_avatar.jpg'),
        'registration_date': registration_date
    }

    # Pass the has_password_provider flag to the template
    return render_template('profile.html', user_info=user_info, form=form, has_password_provider=has_password_provider)
