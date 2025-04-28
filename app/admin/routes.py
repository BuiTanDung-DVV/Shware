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
            .where('last_login', '>', thirty_days_ago)\
            .count().get()
        active_users = active_users_count[0][0].value if active_users_count else 0

        # Lấy thống kê đăng ký theo tháng
        six_months_ago = datetime.now() - timedelta(days=180)
        monthly_counts = {}
        
        users_ref = db_firestore.collection('users')\
            .where('created_at', '>', six_months_ago)\
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
