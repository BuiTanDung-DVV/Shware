import os
from flask import Blueprint, render_template, flash, redirect, url_for, request, abort
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from flask_login import login_required, current_user

files_bp = Blueprint('files', __name__)

# Google Drive Setup
SCOPES = ['https://www.googleapis.com/auth/drive']

creds = Credentials.from_service_account_file(os.getenv('ADMIN_SDK_PATH'), scopes=SCOPES)
service = build('drive', 'v3', credentials=creds)

# Firebase Setup
if not firebase_admin._apps:
    cred = credentials.Certificate(os.getenv('ADMIN_SDK_PATH'))
    firebase_admin.initialize_app(cred)
db = firestore.client()


@files_bp.route('/files')
def list_files():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 5

        # Thêm tham số sort_by và sort_direction
        sort_by = request.args.get('sort_by', 'upload_date')
        sort_direction = request.args.get('sort_direction', 'desc')

        # Danh sách các trường hợp lệ để tránh lỗi bảo mật
        valid_sort_fields = ['title', 'author', 'file_type', 'file_size', 'upload_date']
        if sort_by not in valid_sort_fields:
            sort_by = 'upload_date'  # Mặc định

        valid_directions = ['asc', 'desc']
        if sort_direction not in valid_directions:
            sort_direction = 'desc'  # Mặc định

        # Xây dựng truy vấn với sắp xếp
        query = db.collection('files')

        # Thêm lọc tags nếu được chỉ định
        tag_filter = request.args.get('tag')
        if tag_filter:
            query = query.where(filter=firestore.FieldFilter('tags', 'array_contains', tag_filter))

        # Thêm lọc file_type nếu được chỉ định
        file_type_filter = request.args.get('file_type')
        if file_type_filter:
            query = query.where(filter=firestore.FieldFilter('file_type', '==', file_type_filter))

        # Thêm sắp xếp
        direction = firestore.Query.DESCENDING if sort_direction == 'desc' else firestore.Query.ASCENDING
        query = query.order_by(sort_by, direction=direction)

        # Thực hiện phân trang
        query = query.offset((page - 1) * per_page).limit(per_page)

        files = []
        
        # Thêm sắp xếp theo upload_date giảm dần (mới nhất lên đầu)
        docs = db.collection('files') \
            .order_by('upload_date', direction=firestore.Query.DESCENDING) \
            .offset((page - 1) * per_page) \
            .limit(per_page) \
            .stream()

        for doc in docs:
            data = doc.to_dict()
            files.append({
                'doc_id': doc.id,
                'title': data.get('title'),
                'author': data.get('author'),
                'email': data.get('email'),
                'profile_pic': data.get('profile_pic'),
                'description': data.get('description'),
                'file_type': data.get('file_type'),
                'file_size': data.get('file_size'),
                'tags': data.get('tags', []),  # Giữ nguyên danh sách để dễ truy cập
                'tags_str': ', '.join(data.get('tags', [])),
                'upload_date': data.get('upload_date'),
                'download_url': data.get('download_url'),
                'drive_file_id': data.get('drive_file_id')
            })

        # Get total file count for pagination
        # Áp dụng các bộ lọc tương tự cho việc đếm tổng số tệp
        count_query = db.collection('files')
        if tag_filter:
            count_query = count_query.where(filter=firestore.FieldFilter('tags', 'array_contains', tag_filter))
        if file_type_filter:
            count_query = count_query.where(filter=firestore.FieldFilter('file_type', '==', file_type_filter))

        total_files = len(list(count_query.stream()))
        total_pages = (total_files + per_page - 1) // per_page

        # Lấy tất cả loại file để hiển thị bộ lọc
        all_file_types = set()
        all_tags = set()

        # Lấy một số lượng giới hạn để tránh quá tải
        type_docs = db.collection('files').limit(100).stream()
        for doc in type_docs:
            data = doc.to_dict()
            all_file_types.add(data.get('file_type'))
            for tag in data.get('tags', []):
                all_tags.add(tag)

    except Exception as e:
        flash(f'Không thể tải danh sách tệp: {str(e)}')
        files = []
        total_pages = 1
        all_file_types = set()
        all_tags = set()
        sort_by = 'upload_date'
        sort_direction = 'desc'
        tag_filter = None
        file_type_filter = None

    return render_template('files.html',
                           files=files,
                           page=page,
                           total_pages=total_pages,
                           sort_by=sort_by,
                           sort_direction=sort_direction,
                           all_file_types=sorted(all_file_types),
                           all_tags=sorted(all_tags),
                           current_tag=tag_filter,
                           current_file_type=file_type_filter)
@files_bp.route('/delete/<doc_id>', methods=['POST'])
def delete_file(doc_id):
    try:
        doc_ref = db.collection('files').document(doc_id)
        doc = doc_ref.get()
        if not doc.exists:
            flash('Không tìm thấy tệp để xóa!')
            return redirect(url_for('user_profile.profile', _anchor='uploads'))

        drive_file_id = doc.to_dict().get('drive_file_id')
        if drive_file_id:
            try:
                service.files().delete(fileId=drive_file_id).execute()
            except Exception as e:
                flash(f'Không thể xóa file trên Google Drive: {str(e)}')

        doc_ref.delete()
        flash('Tệp đã được xóa thành công!', 'success')
    except Exception as e:
        flash(f'Không thể xóa tệp: {str(e)}', 'error')

    # Redirect back to the profile page, specifically targeting the uploads tab
    return redirect(url_for('user_profile.profile', _anchor='uploads'))

@files_bp.route('/file/<string:doc_id>')
def file_detail(doc_id):
    """Displays the detail page for a specific file."""
    try:
        file_ref = db.collection('files').document(doc_id)
        file_doc = file_ref.get()

        if not file_doc.exists:
            abort(404) # Not found

        file_data = file_doc.to_dict()
        file_data['doc_id'] = doc_id # Add doc_id for potential use in template

        # Assuming upload_date is stored as ISO string, convert to datetime object if needed for display formatting
        if 'upload_date' in file_data and isinstance(file_data['upload_date'], str):
             try:
                 file_data['upload_date'] = datetime.fromisoformat(file_data['upload_date'])
             except ValueError:
                 # Handle cases where the date string might not be in the expected ISO format
                 file_data['upload_date'] = None # Or keep the original string, or log an error

        # Use the thumbnail_url from Firestore if available, otherwise use default placeholder
        if 'thumbnail_url' not in file_data or not file_data['thumbnail_url']:
            file_data['thumbnail_url'] = url_for('static', filename='default_placeholder.png')

        # Get user's review if they've reviewed this file
        user_review = None
        if current_user.is_authenticated:
            # Updated query using filter keyword argument
            user_reviews_query = db.collection('reviews') \
                .where(filter=firestore.FieldFilter('user_email', '==', current_user.email)) \
                .where(filter=firestore.FieldFilter('file_id', '==', doc_id)) \
                .limit(1)
            user_reviews = user_reviews_query.stream()
            for review in user_reviews:
                user_review = review.to_dict()
                user_review['review_id'] = review.id
                break

        return render_template('file_detail.html', file=file_data, user_review=user_review)

    except Exception as e:
        flash(f'Lỗi khi tải chi tiết tệp: {str(e)}', 'error')
        # Redirect to a safe page, like the file list or home
        return redirect(url_for('user_profile.profile', _anchor='uploads'))

@files_bp.route('/file/<string:doc_id>/review', methods=['POST'])
@login_required
def submit_review(doc_id):
    """Submit or update a review for a file."""
    try:
        rating = request.form.get('rating', type=int)
        
        # Validate rating
        if not rating or rating < 1 or rating > 5:
            flash('Vui lòng chọn xếp hạng từ 1 đến 5 sao.', 'warning')
            return redirect(url_for('files.file_detail', doc_id=doc_id))
        
        # Check if user has already reviewed this file
        # Updated query using filter keyword argument
        user_reviews_query = db.collection('reviews') \
            .where(filter=firestore.FieldFilter('user_email', '==', current_user.email)) \
            .where(filter=firestore.FieldFilter('file_id', '==', doc_id)) \
            .limit(1)
        user_reviews = user_reviews_query.stream()
        
        review_exists = False
        old_rating = 0
        
        for review in user_reviews:
            review_exists = True
            review_ref = db.collection('reviews').document(review.id)
            old_review = review.to_dict()
            old_rating = old_review.get('rating', 0)
            
            # Update the existing review
            review_ref.update({
                'rating': rating,
                'updated_at': datetime.utcnow().isoformat()
            })
            break
        
        # Get the file document to update average rating
        file_ref = db.collection('files').document(doc_id)
        file_doc = file_ref.get()
        
        if not file_doc.exists:
            flash('Không tìm thấy tệp để đánh giá!', 'error')
            redirect(url_for('main.home'))
        
        file_data = file_doc.to_dict()
        
        # Update the file's average rating
        total_reviews = file_data.get('total_reviews', 0)
        total_rating_sum = file_data.get('total_rating_sum', 0)
        
        if not review_exists:
            # This is a new review
            total_reviews += 1
            total_rating_sum += rating
            
            # Create a new review document
            db.collection('reviews').add({
                'file_id': doc_id,
                'user_email': current_user.email,
                'user_name': current_user.name,
                'rating': rating,
                'created_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat()
            })
        else:
            # This is an update to an existing review
            # Subtract the old rating and add the new one
            total_rating_sum = total_rating_sum - old_rating + rating
        
        # Calculate new average rating
        avg_rating = total_rating_sum / total_reviews if total_reviews > 0 else 0
        
        # Update the file document with new rating data
        file_ref.update({
            'avg_rating': avg_rating,
            'total_reviews': total_reviews,
            'total_rating_sum': total_rating_sum
        })
        
        flash('Cảm ơn bạn đã đánh giá!', 'success')
        return redirect(url_for('files.file_detail', doc_id=doc_id))
        
    except Exception as e:
        flash(f'Lỗi khi gửi đánh giá: {str(e)}', 'error')
        return redirect(url_for('files.file_detail', doc_id=doc_id))
