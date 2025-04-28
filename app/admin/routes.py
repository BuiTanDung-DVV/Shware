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

from app.models.user import User

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
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    try:
        # Lấy tổng số người dùng từ Firestore
        users_ref = db_firestore.collection('users')
        total_users = len(list(users_ref.stream()))
        total_pages = ceil(total_users / per_page)
        
        # Đảm bảo page nằm trong khoảng hợp lệ
        if page < 1:
            page = 1
        elif page > total_pages and total_pages > 0:
            page = total_pages
        
        # Lấy danh sách người dùng cho trang hiện tại
        users = []
        users_query = users_ref.order_by('created_at', direction=firestore.Query.DESCENDING)\
            .offset((page - 1) * per_page)\
            .limit(per_page)
            
        for doc in users_query.stream():
            user_data = doc.to_dict()
            user_data['id'] = doc.id
            
            # Lấy thêm thông tin từ Firebase Auth
            try:
                firebase_user = firebase_auth.get_user(doc.id)
                user_data['disabled'] = firebase_user.disabled
                user_data['email'] = firebase_user.email
                user_data['display_name'] = firebase_user.display_name
                user_data['photo_url'] = firebase_user.photo_url
                user_data['registration_date'] = firebase_user.user_metadata.creation_timestamp
            except:
                user_data['disabled'] = False
                
            users.append(user_data)
            
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
                           
    except Exception as e:
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

@admin_bp.route('/files')
@login_required
@admin_required
def manage_files():
    try:
        files = []
        files_ref = db_firestore.collection('files')\
            .order_by('upload_date', direction=firestore.Query.DESCENDING)\
            .stream()
        
        for doc in files_ref:
            file_data = doc.to_dict()
            file_data['id'] = doc.id
            files.append(file_data)
            
        return render_template('admin_files.html', files=files)
    except Exception as e:
        flash(f'Error loading files: {str(e)}', 'danger')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/manage_file', methods=['POST'])
@login_required
@admin_required
def manage_file():
    try:
        data = request.get_json()
        file_id = data.get('fileId')
        action = data.get('action')

        if action == 'delete':
            # Delete from Firestore
            db_firestore.collection('files').document(file_id).delete()
            
            # Delete from Google Drive if applicable
            try:
                file_data = db_firestore.collection('files').document(file_id).get().to_dict()
                if file_data and 'drive_id' in file_data:
                    service = build('drive', 'v3', credentials=creds)
                    service.files().delete(fileId=file_data['drive_id']).execute()
            except Exception as e:
                print(f"Error deleting from Drive: {e}")

            return jsonify({'success': True})
        elif action == 'toggleVisibility':
            visibility = data.get('visibility', False)
            db_firestore.collection('files').document(file_id).update({
                'is_public': visibility
            })
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Invalid action'}), 400

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# @admin_bp.route('/posts')
# @login_required
# @admin_required
# def manage_posts():
#     try:
#         posts = []
#         posts_ref = db_firestore.collection('posts')\
#             .order_by('created_at', direction=firestore.Query.DESCENDING)\
#             .stream()
        
#         for doc in posts_ref:
#             post_data = doc.to_dict()
#             post_data['id'] = doc.id
#             posts.append(post_data)
            
#         return render_template('admin_posts.html', posts=posts)
#     except Exception as e:
#         flash(f'Error loading posts: {str(e)}', 'danger')
#         return redirect(url_for('admin.dashboard'))

# @admin_bp.route('/manage_post', methods=['POST'])
# @login_required
# @admin_required
# def manage_post():
#     try:
#         data = request.get_json()
#         post_id = data.get('postId')
#         action = data.get('action')

#         if action == 'delete':
#             # Delete from Firestore
#             post_ref = db_firestore.collection('posts').document(post_id)
#             post_data = post_ref.get().to_dict()
            
#             # Delete associated files if any
#             if post_data and 'file_info' in post_data:
#                 try:
#                     service = build('drive', 'v3', credentials=creds)
#                     for file_info in post_data['file_info']:
#                         if 'drive_id' in file_info:
#                             service.files().delete(fileId=file_info['drive_id']).execute()
#                 except Exception as e:
#                     print(f"Error deleting post files from Drive: {e}")
            
#             # Finally delete the post document
#             post_ref.delete()
            
#             return jsonify({'success': True})
            
#         elif action == 'toggleVisibility':
#             visibility = data.get('visibility', False)
#             db_firestore.collection('posts').document(post_id).update({
#                 'is_public': visibility
#             })
#             return jsonify({'success': True})
            
#         elif action == 'updateFeatured':
#             featured = data.get('featured', False)
#             db_firestore.collection('posts').document(post_id).update({
#                 'featured': featured
#             })
#             return jsonify({'success': True})
            
#         else:
#             return jsonify({'success': False, 'error': 'Invalid action'}), 400

#     except Exception as e:
#         return jsonify({'success': False, 'error': str(e)}), 500

# Dashboard statistics endpoint
@admin_bp.route('/stats')
@login_required
@admin_required
def get_stats():
    try:
        print(f"Total users: {total_users}")
        total_users = db_firestore.collection('users').count().get()[0][0]
        total_files = db_firestore.collection('files').count().get()[0][0]
        # total_posts = db_firestore.collection('posts').count().get()[0][0]

        
        # Get active users in last 30 days
        thirty_days_ago = datetime.now() - timedelta(days=30)
        active_users = db_firestore.collection('users')\
            .where('last_login', '>', thirty_days_ago)\
            .count().get()[0][0]

        # Get monthly user registrations for the past 6 months
        six_months_ago = datetime.now() - timedelta(days=180)
        user_registrations = []
        
        users_ref = db_firestore.collection('users')\
            .where('created_at', '>', six_months_ago)\
            .order_by('created_at')\
            .stream()
            
        monthly_counts = {}
        for user in users_ref:
            user_data = user.to_dict()
            if 'created_at' in user_data:
                month = user_data['created_at'].strftime('%Y-%m')
                monthly_counts[month] = monthly_counts.get(month, 0) + 1

        # Prepare data for the last 6 months
        months = []
        counts = []
        current = datetime.now()
        for i in range(5, -1, -1):
            month = (current - timedelta(days=30*i)).strftime('%Y-%m')
            months.append(month)
            counts.append(monthly_counts.get(month, 0))

        # Get activity distribution
        files_count = total_files
        # posts_count = total_posts
        comments_count = db_firestore.collection('comments').count().get()[0][0] if 'comments' in [col.id for col in db_firestore.collections()] else 0

        return jsonify({
            'total_users': total_users,
            'total_files': total_files,
            # 'total_posts': total_posts,
            'active_users': active_users,
            'registration_trend': {
                'labels': months,
                'data': counts
            },
            'activity_distribution': {
                'labels': ['Files', 'Posts', 'Comments'],
                # 'data': [files_count, posts_count, comments_count]
                'data': [files_count, comments_count]
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
