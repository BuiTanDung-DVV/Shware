import os
from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for
from flask_login import login_required, current_user
import firebase_admin
from firebase_admin import auth as firebase_auth, firestore
from functools import wraps
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from math import ceil
import random
from flask import current_app

from app.utils.color_generator import generate_colors

admin_bp = Blueprint('admin', __name__)
db_firestore = firestore.client()

# Google Drive Setup
SCOPES = ['https://www.googleapis.com/auth/drive']

creds = Credentials.from_service_account_file(os.getenv('ADMIN_SDK_PATH'), scopes=SCOPES)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Bạn không có quyền truy cập trang này.', 'danger')
            return redirect(url_for('main.home'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    return render_template('admin.html')

@admin_bp.route('/users')
@login_required
@admin_required
def manage_users():
    try:
        # Lấy tham số trang và đảm bảo nó là số nguyên dương
        try:
            page = int(request.args.get('page', 1))
            if page < 1:
                page = 1
        except (ValueError, TypeError):
            page = 1
            
        per_page = 10
        
        # Lấy tổng số người dùng từ Firestore
        try:
            users_ref = db_firestore.collection('users')
            users_stream = users_ref.stream()
            total_users = sum(1 for _ in users_stream)
            total_pages = ceil(total_users / per_page) if total_users > 0 else 1
            
            # Đảm bảo page nằm trong khoảng hợp lệ
            page = min(page, total_pages)
            
            # Lấy danh sách người dùng cho trang hiện tại
            users = []
            users_query = users_ref.order_by('created_at', direction=firestore.Query.DESCENDING)\
                .offset((page - 1) * per_page)\
                .limit(per_page)
                
            # Lấy danh sách user IDs để batch lookup
            user_ids = []
            for doc in users_query.stream():
                try:
                    user_data = doc.to_dict()
                    user_data['id'] = doc.id
                    user_ids.append(doc.id)
                    users.append(user_data)
                except Exception as doc_error:
                    print(f"Error processing document {doc.id}: {str(doc_error)}")
                    continue
            
            # Batch lookup user info from Firebase Auth
            try:
                if user_ids:
                    firebase_users = firebase_auth.get_users(user_ids)
                    user_info_map = {user.uid: user for user in firebase_users.users}
                    
                    # Update user data with Firebase Auth info
                    for user in users:
                        if user['id'] in user_info_map:
                            firebase_user = user_info_map[user['id']]
                            user['disabled'] = firebase_user.disabled
                            user['email'] = firebase_user.email
                            user['display_name'] = firebase_user.name
                            user['photo_url'] = firebase_user.photo_url
                            user['registration_date'] = firebase_user.user_metadata.creation_timestamp
                        else:
                            user['disabled'] = False
                            user['email'] = user.get('email', '')
                            user['display_name'] = user.get('name', '')
                            user['photo_url'] = user.get('profile_pic', '')
                            user['registration_date'] = user.get('created_at', None)
            except Exception as auth_error:
                print(f"Error getting Firebase Auth data: {str(auth_error)}")
                # If Firebase Auth lookup fails, use Firestore data only
                for user in users:
                    user['disabled'] = False
                    user['email'] = user.get('email', '')
                    user['display_name'] = user.get('name', '')
                    user['photo_url'] = user.get('profile_pic', '')
                    user['registration_date'] = user.get('created_at', None)
                    
            # Tính toán các thông số cho phân trang
            has_prev = page > 1
            has_next = page < total_pages
            prev_page = page - 1 if has_prev else None
            next_page = page + 1 if has_next else None
            
            # Tạo danh sách các số trang để hiển thị
            pages = []
            if total_pages <= 7:
                pages = list(range(1, total_pages + 1))
            else:
                if page <= 4:
                    pages = list(range(1, 6)) + ['...', total_pages]
                elif page >= total_pages - 3:
                    pages = [1, '...'] + list(range(total_pages - 4, total_pages + 1))
                else:
                    pages = [1, '...'] + list(range(page - 1, page + 2)) + ['...', total_pages]
                    
            return render_template('admin_users.html', 
                               users=users,
                               page=page,
                               total_pages=total_pages,
                               has_prev=has_prev,
                               has_next=has_next,
                               prev_page=prev_page,
                               next_page=next_page,
                               pages=pages)
                               
        except Exception as firestore_error:
            print(f"Firestore error: {str(firestore_error)}")
            raise firestore_error
            
    except Exception as e:
        print(f"General error: {str(e)}")
        flash(f'Lỗi khi tải danh sách người dùng: {str(e)}', 'danger')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/manage_user', methods=['POST'])
@login_required
@admin_required
def manage_user():
    try:
        data = request.get_json()
        user_id = data.get('userId')
        action = data.get('action')

        if user_id == current_user.id:
            return jsonify({'success': False, 'error': 'Không thể chỉnh sửa tài khoản của chính mình'}), 400

        # Kiểm tra user tồn tại
        try:
            firebase_user = firebase_auth.get_user(user_id)
        except:
            return jsonify({'success': False, 'error': 'Không tìm thấy người dùng'}), 404

        if action == 'updateRole':
            new_role = data.get('role')
            if new_role not in ['user', 'admin']:
                return jsonify({'success': False, 'error': 'Vai trò không hợp lệ'}), 400

            # Cập nhật role trong Firestore
            db_firestore.collection('users').document(user_id).update({
                'role': new_role
            })

            # Cập nhật custom claims trong Firebase Auth
            firebase_auth.set_custom_user_claims(user_id, {'role': new_role})

        elif action == 'updateStatus':
            print(f"Updating status for user {user_id}")
            disabled = data.get('disabled', False)
            
            # Cập nhật trong Firebase Auth
            firebase_auth.update_user(user_id, disabled=disabled)

            # Cập nhật trong Firestore
            db_firestore.collection('users').document(user_id).update({
                'disabled': disabled
            })

        elif action == 'deleteUser':
            # Xóa từ Firebase Auth
            firebase_auth.delete_user(user_id)

            # Xóa từ Firestore
            db_firestore.collection('users').document(user_id).delete()

        else:
            return jsonify({'success': False, 'error': 'Hành động không hợp lệ'}), 400

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/admin_files')
@login_required
@admin_required
def manage_files():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 15

        # Get total count of files
        files_count_ref = db_firestore.collection('files').count().get()
        total_files = files_count_ref[0][0].value if files_count_ref else 0
        total_pages = (total_files + per_page - 1) // per_page  # Ceiling division

        # Ensure page is within valid range
        if page < 1:
            page = 1
        elif page > total_pages and total_pages > 0:
            page = total_pages

        # Get files for current page
        files = []
        files_ref = db_firestore.collection('files')\
            .order_by('upload_date', direction=firestore.Query.DESCENDING)\
            .offset((page - 1) * per_page)\
            .limit(per_page)\
            .stream()
        
        for doc in files_ref:
            file_data = doc.to_dict()
            file_data['id'] = doc.id
            files.append(file_data)

        # Calculate pagination info
        has_prev = page > 1
        has_next = page < total_pages
        prev_page = page - 1 if has_prev else None
        next_page = page + 1 if has_next else None

        # Generate page numbers to display
        pages = []
        if total_pages <= 7:
            # If total pages is 7 or less, show all pages
            pages = list(range(1, total_pages + 1))
        else:
            # If current page is near the start
            if page <= 4:
                pages = list(range(1, 6)) + ['...', total_pages]
            # If current page is near the end
            elif page >= total_pages - 3:
                pages = [1, '...'] + list(range(total_pages - 4, total_pages + 1))
            # If current page is in the middle
            else:
                pages = [1, '...'] + list(range(page - 1, page + 2)) + ['...', total_pages]

        return render_template('admin_files.html',
                           files=files,
                           page=page,
                           total_pages=total_pages,
                           has_prev=has_prev,
                           has_next=has_next,
                           prev_page=prev_page,
                           next_page=next_page,
                           pages=pages)
    except Exception as e:
        flash(f'Error loading files: {str(e)}', 'danger')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/manage_file', methods=['POST'])
@login_required
@admin_required
def manage_file():
    try:
        # Get data from request
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data received'}), 400
            
        file_id = data.get('fileId')
        action = data.get('action')
        
        if not file_id:
            return jsonify({'success': False, 'error': 'No file ID provided'}), 400
            
        # Verify file exists
        file_ref = db_firestore.collection('files').document(file_id)
        file_doc = file_ref.get()
        if not file_doc.exists:
            return jsonify({'success': False, 'error': 'File not found'}), 404

        if action == 'delete':
            # Delete from Firestore
            file_ref.delete()
            
            # Delete from Google Drive if applicable
            try:
                file_data = file_doc.to_dict()
                if file_data and 'drive_id' in file_data:
                    service = build('drive', 'v3', credentials=creds)
                    service.files().delete(fileId=file_data['drive_id']).execute()
            except Exception as e:
                print(f"Error deleting from Drive: {e}")

            return jsonify({'success': True})

        elif action == 'toggleApprove':
            approve = data.get('approve')
            if approve is None:  # Check if approve was provided
                return jsonify({'success': False, 'error': 'Approve status not provided'}), 400
                
            try:
                file_ref.update({
                    'approve': approve
                })
                return jsonify({'success': True})
            except Exception as e:
                print(f"Error updating approve status: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500

        elif action == 'toggleVisibility':
            visibility = data.get('visibility')
            if visibility is None:  # Check if visibility was provided
                return jsonify({'success': False, 'error': 'Visibility status not provided'}), 400
                
            try:
                file_ref.update({
                    'visibility': visibility
                })
                return jsonify({'success': True})
            except Exception as e:
                print(f"Error updating visibility: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500
            
        else:
            return jsonify({'success': False, 'error': 'Invalid action'}), 400

    except Exception as e:
        print(f"Error in manage_file: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/stats')
@login_required
@admin_required
def get_stats():
    default_response = {
        'total_users': 0,
        'total_files': 0,
        'active_users': 0,
        'registration_trend': {
            'labels': [],
            'data': []
        },
        'activity_distribution': {
            'labels': [],
            'data': [],
            'backgroundColor': []
        }
    }
    
    try:
        # Đếm tổng số users
        users_count = db_firestore.collection('users').count().get()
        total_users = users_count[0][0].value if users_count else 0
        
        # Đếm tổng số files
        files_count = db_firestore.collection('files').count().get()
        total_files = files_count[0][0].value if files_count else 0
        
        # Đếm số user active trong 30 ngày
        thirty_days_ago = datetime.now() - timedelta(days=30)
        active_users_count = db_firestore.collection('users')\
            .where(filter=firestore.FieldFilter('last_login', '>', thirty_days_ago))\
            .count().get()
        active_users = active_users_count[0][0].value if active_users_count else 0

        # Lấy thống kê đăng ký theo tháng
        six_months_ago = datetime.now() - timedelta(days=180)
        monthly_counts = {}
        
        users_ref = db_firestore.collection('users')\
            .where(filter=firestore.FieldFilter('created_at', '>', six_months_ago))\
            .order_by('created_at')\
            .stream()
            
        for user in users_ref:
            user_data = user.to_dict()
            if 'created_at' in user_data:
                month = user_data['created_at'].strftime('%Y-%m')
                monthly_counts[month] = monthly_counts.get(month, 0) + 1

        # Chuẩn bị dữ liệu 6 tháng gần nhất
        months = []
        counts = []
        current = datetime.now()
        for i in range(5, -1, -1):
            month = (current - timedelta(days=30*i)).strftime('%Y-%m')
            months.append(month)
            counts.append(monthly_counts.get(month, 0))

        # Lấy thống kê về tags và số lượng file sử dụng
        tags_ref = db_firestore.collection('tags').stream()
        tag_stats = []
        for tag in tags_ref:
            tag_data = tag.to_dict()
            if 'references' in tag_data:
                tag_stats.append({
                    'name': tag_data['name'],
                    'count': tag_data['references']
                })
        
        # Sắp xếp theo số lượng sử dụng từ cao đến thấp
        tag_stats.sort(key=lambda x: x['count'], reverse=True)
        
        # Generate colors for all tags
        colors = generate_colors(len(tag_stats))

        return jsonify({
            'total_users': total_users,
            'total_files': total_files,
            'active_users': active_users,
            'registration_trend': {
                'labels': months,
                'data': counts
            },
            'activity_distribution': {
                'labels': [tag['name'] for tag in tag_stats],
                'data': [tag['count'] for tag in tag_stats],
                'backgroundColor': colors
            }
        })
    except Exception as e:
        print(f"Error in get_stats: {str(e)}")
        return jsonify(default_response), 500

@admin_bp.route('/subscription-trend')
@login_required
def subscription_trend():
    try:
        # Get the last 30 days of data
        end_date = datetime.now().replace(tzinfo=None)  # Make timezone-naive
        start_date = end_date - timedelta(days=30)
        
        print(f"\n=== Subscription Trend Analysis ===")
        print(f"Date Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        
        # Query Firestore for subscription data
        users_ref = db_firestore.collection('users')
        users = users_ref.get()
        print(f"Total users found: {len(users)}")
        
        # Initialize daily counts
        daily_counts = {}
        current_date = start_date
        while current_date <= end_date:
            daily_counts[current_date.strftime('%Y-%m-%d')] = {
                'new_subscriptions': 0,
                'active_subscriptions': 0,
                'cancelled_subscriptions': 0
            }
            current_date += timedelta(days=1)
        
        # Count subscriptions
        for user in users:
            user_data = user.to_dict()
            subscription_start = user_data.get('subscription_start_date')
            subscription_end = user_data.get('subscription_end_date')
            subscription_status = user_data.get('subscription_status', '')
            
            if subscription_start:
                # Convert Firestore timestamp to datetime
                if hasattr(subscription_start, 'timestamp'):
                    start_date_obj = subscription_start.replace(tzinfo=None)  # Make timezone-naive
                else:
                    start_date_obj = datetime.fromtimestamp(subscription_start)
                start_date_str = start_date_obj.strftime('%Y-%m-%d')
                if start_date_str in daily_counts:
                    daily_counts[start_date_str]['new_subscriptions'] += 1
            
            if subscription_start and subscription_end:
                # Convert Firestore timestamps to datetime
                if hasattr(subscription_start, 'timestamp'):
                    current_date = subscription_start.replace(tzinfo=None)  # Make timezone-naive
                else:
                    current_date = datetime.fromtimestamp(subscription_start)
                
                if hasattr(subscription_end, 'timestamp'):
                    end_date_obj = subscription_end.replace(tzinfo=None)  # Make timezone-naive
                else:
                    end_date_obj = datetime.fromtimestamp(subscription_end)
                
                while current_date <= end_date_obj and current_date <= end_date:
                    date_str = current_date.strftime('%Y-%m-%d')
                    if date_str in daily_counts:
                        daily_counts[date_str]['active_subscriptions'] += 1
                    current_date += timedelta(days=1)
            
            # Count cancelled subscriptions
            if subscription_status == 'cancelled':
                if subscription_end:
                    # Convert Firestore timestamp to datetime
                    if hasattr(subscription_end, 'timestamp'):
                        cancel_date = subscription_end.replace(tzinfo=None)  # Make timezone-naive
                    else:
                        cancel_date = datetime.fromtimestamp(subscription_end)
                    cancel_date_str = cancel_date.strftime('%Y-%m-%d')
                    if cancel_date_str in daily_counts:
                        daily_counts[cancel_date_str]['cancelled_subscriptions'] += 1
        
        # Format data for Chart.js
        dates = list(daily_counts.keys())
        new_subs = [daily_counts[date]['new_subscriptions'] for date in dates]
        active_subs = [daily_counts[date]['active_subscriptions'] for date in dates]
        cancelled_subs = [daily_counts[date]['cancelled_subscriptions'] for date in dates]
        
        # Print detailed statistics
        print("\nDaily Statistics:")
        for date in dates:
            stats = daily_counts[date]
            if stats['new_subscriptions'] > 0 or stats['active_subscriptions'] > 0 or stats['cancelled_subscriptions'] > 0:
                print(f"{date}:")
                print(f"  New: {stats['new_subscriptions']}")
                print(f"  Active: {stats['active_subscriptions']}")
                print(f"  Cancelled: {stats['cancelled_subscriptions']}")
        
        print("\nSummary:")
        print(f"Total new subscriptions: {sum(new_subs)}")
        print(f"Total active subscriptions: {sum(active_subs)}")
        print(f"Total cancelled subscriptions: {sum(cancelled_subs)}")
        print("===============================\n")
        
        return jsonify({
            'dates': dates,
            'new_subscriptions': new_subs,
            'active_subscriptions': active_subs,
            'cancelled_subscriptions': cancelled_subs
        })
    except Exception as e:
        print(f"Error in subscription_trend: {str(e)}")
        return jsonify({'error': str(e)}), 500
