from flask import render_template, session, redirect, url_for, flash, Blueprint, request
from firebase_admin import firestore, auth as firebase_auth
from flask_login import login_required, current_user
from ..auth.forms import ProfileUpdateForm
from ..models.user import User
from ..files_management.upload import upload_progress
from datetime import datetime

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

        display_name = form.display_name.data
        if display_name and display_name != (firebase_user.display_name or ''):
            try:
                # Update Firebase Auth
                firebase_auth.update_user(user_id, display_name=display_name)

                # Update Firestore 'users' collection
                try:
                    db_firestore.collection('users').document(user_id).update({'name': display_name})
                except Exception as firestore_e:
                    flash(f'Error updating Firestore profile name: {firestore_e}', 'warning')

                flash('Display name updated successfully.', 'success')
                firebase_user = firebase_auth.get_user(user_id) # Refresh user data
            except Exception as e:
                flash(f'Error updating display name: {e}', 'danger')

        # --- Update Password Logic (only if user has password provider and fields submitted) ---
        new_password = form.new_password.data
        if has_password_provider and new_password:
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

    # Fetch user uploads from Firestore
    user_uploads = []
    try:
        uploads_query = db_firestore.collection('files').where('author_id', '==', user_id).order_by('upload_date', direction=firestore.Query.DESCENDING).stream()
            
        for doc in uploads_query:
            file_data = doc.to_dict()
            file_data['doc_id'] = doc.id
            
            # Add upload progress from cache if available
            if file_data.get('upload_id') in upload_progress:
                progress_data = upload_progress[file_data['upload_id']]
                file_data['upload_progress'] = progress_data.get('progress', 0)
                
            user_uploads.append(file_data)
    except Exception as e:
        flash(f"Error fetching user uploads: {e}", "danger")

    return render_template('profile.html', user_info=user_info, form=form, 
                         has_password_provider=has_password_provider, 
                         user_uploads=user_uploads)

@user_profile_bp.route('/subscription')
@login_required
def subscription():
    # Get payment history
    payment_history = []
    try:
        payments_query = db_firestore.collection('payments').where('user_id', '==', current_user.id).order_by('created_at', direction=firestore.Query.DESCENDING).stream()
        for doc in payments_query:
            payment_data = doc.to_dict()
            payment_data['doc_id'] = doc.id
            payment_history.append(payment_data)
    except Exception as e:
        flash(f"Error fetching payment history: {e}", "danger")

    return render_template('subscription.html', payment_history=payment_history)

@user_profile_bp.route('/cancel-subscription', methods=['POST'])
@login_required
def cancel_subscription():
    try:
        # Update subscription status in Firestore
        db_firestore.collection('users').document(current_user.id).update({
            'subscription_status': 'cancelled',
            'subscription_cancelled_at': datetime.now()
        })
        
        flash('Your subscription has been cancelled. It will remain active until the end of your current billing period.', 'success')
    except Exception as e:
        flash(f'Error cancelling subscription: {e}', 'danger')
    
    return redirect(url_for('user_profile.subscription'))
