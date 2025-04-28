import os
import io
import math
import threading
import time
import uuid
from flask import Blueprint, request, redirect, render_template, flash, url_for, jsonify, session
from flask_login import login_required, current_user
# from app import limiter
from werkzeug.utils import secure_filename
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import cloudinary
import cloudinary.uploader
import cloudinary.api

upload_bp = Blueprint('upload', __name__)

# Google Drive Setup
SCOPES = ['https://www.googleapis.com/auth/drive']
FOLDER_ID = os.getenv('GGDRIVE_FOLDER_ID')
ALLOWED_EXTENSIONS = {'zip', 'rar'}

creds = Credentials.from_service_account_file(os.getenv('ADMIN_SDK_PATH'), scopes=SCOPES)
service = build('drive', 'v3', credentials=creds)

# Firebase Setup
if not firebase_admin._apps:
    firebase_cred = credentials.Certificate(os.getenv('ADMIN_SDK_PATH'))
    firebase_admin.initialize_app(firebase_cred)
db = firestore.client()

# Cloudinary Setup
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
    secure=True
)

# Dictionary to track upload progress
upload_progress = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def upload_thumbnail_to_cloudinary(file, title):
    """Upload thumbnail to Cloudinary and return the URL"""
    try:
        # Tạo tên file an toàn từ tiêu đề
        safe_title = secure_filename(title)
        # Upload to Cloudinary
        upload_result = cloudinary.uploader.upload(
            file,
            folder="filestore_thumbnails",
            public_id=f"thumb_{safe_title}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            overwrite=True,
            resource_type="image"
        )
        return upload_result.get('secure_url')
    except Exception as e:
        print(f"Cloudinary upload error: {e}")
        return None


def background_upload_task(upload_id, file_content, filename, title, description, tags, thumbnail_url, current_user_id, current_user_name, current_user_email, current_user_profile_pic, doc_id):
    """Hàm xử lý quá trình tải lên nền với theo dõi tiến độ thực tế"""
    try:
        upload_progress[upload_id]['status'] = 'uploading'
        upload_progress[upload_id]['progress'] = 0

        file_size = len(file_content)
        # Chuẩn bị tải lên Google Drive
        file_metadata = {
            'name': filename,
            'parents': [FOLDER_ID]
        }
        media = MediaIoBaseUpload(io.BytesIO(file_content), mimetype='application/octet-stream', resumable=True)
        request_drive = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        )
        response = None
        while response is None:
            status, response = request_drive.next_chunk()
            if status:
                uploaded = int(status.resumable_progress)
                percent = int((uploaded / file_size) * 85) if file_size else 85
                upload_progress[upload_id]['progress'] = min(percent, 85)  # Tối đa 85% khi tải lên
        # Sau khi tải lên xong, đặt tiến độ là 90%
        upload_progress[upload_id]['progress'] = 90

        # Cập nhật tài liệu hiện có trong Firestore
        current_time = datetime.utcnow()
        
        # Xử lý tags
        tag_refs = []
        for tag_name in tags:
            # Tìm tag trong collection tags
            tag_query = db.collection('tags').where(filter=firestore.FieldFilter('name', '==', tag_name.lower())).limit(1).stream()
            tag_doc = None
            for doc in tag_query:
                tag_doc = doc
                break
            
            if tag_doc:
                # Tag đã tồn tại, tăng số references
                tag_ref = db.collection('tags').document(tag_doc.id)
                tag_ref.update({
                    'references': firestore.Increment(1)
                })
                tag_refs.append(tag_ref)
            else:
                # Tag chưa tồn tại, tạo mới
                new_tag_ref = db.collection('tags').add({
                    'name': tag_name.lower(),
                    'references': 1,
                    'created_at': current_time.isoformat()
                })[1]  # [1] là DocumentReference
                tag_refs.append(new_tag_ref)

        db.collection('files').document(doc_id).update({
            'author': current_user_name,
            'author_id': current_user_id,
            'email': current_user_email,
            'profile_pic': current_user_profile_pic,
            'description': description,
            'tags': tags,
            'tag_refs': [ref.id for ref in tag_refs],
            'upload_date': current_time.isoformat(),
            'download_url': response.get('webViewLink'),
            'drive_file_id': response.get('id'),
            'avg_rating': 0,
            'total_reviews': 0,
            'total_rating_sum': 0,
            'upload_status': 'completed',
            'approve': False,  
            'visibility': False  
        })

        upload_progress[upload_id]['progress'] = 100
        upload_progress[upload_id]['status'] = 'completed'
        
        # Xóa mục tiến độ sau khi hoàn tất
        if upload_id in upload_progress:
            del upload_progress[upload_id]
            
    except Exception as e:
        print(f"Lỗi tải lên nền: {e}")
        upload_progress[upload_id]['status'] = 'failed'
        upload_progress[upload_id]['error'] = str(e)
        time.sleep(3600)  # Keep error info available for 1 hour
        if upload_id in upload_progress:
            del upload_progress[upload_id]

        # Nếu có lỗi, cập nhật trạng thái tệp
        try:
            db.collection('files').document(doc_id).update({
                'upload_status': 'failed',
                'error_message': str(e)
            })
        except:
            pass  # Ignore errors when updating error status

@upload_bp.route('/upload_files', methods=['GET', 'POST'])
@login_required
# @limiter.limit("20 per hour")
def upload_file():
    # Lấy tất cả tags từ collection tags, kể cả reference = 0
    all_tags = []
    try:
        tags_docs = db.collection('tags').stream()
        for doc in tags_docs:
            tag_data = doc.to_dict()
            all_tags.append(tag_data.get('name'))
    except Exception as e:
        print(f"Error fetching tags: {e}")
        # Fallback to empty list if there's an error
        all_tags = []

    if request.method == 'POST':
        # Lấy file và thông tin từ form
        file = request.files.get('file')
        thumbnail = request.files.get('thumbnail')
        title = request.form.get('title')
        description = request.form.get('description')
        # Lấy các tag được chọn
        tags = request.form.getlist('tags')

        # Kiểm tra dữ liệu đầu vào - bỏ yêu cầu thumbnail
        if not file or not title or not description or not tags:
            flash('Vui lòng điền đầy đủ thông tin và chọn tệp hợp lệ!', 'error')
            return redirect(request.url)

        if not file or not allowed_file(file.filename):
            flash('Chỉ cho phép tải lên các file có định dạng .zip hoặc .rar', 'error')
            return redirect(request.url)

        try:
            # 1. Upload thumbnail lên Cloudinary hoặc sử dụng mặc định
            if thumbnail and thumbnail.filename:
                thumbnail_url = upload_thumbnail_to_cloudinary(thumbnail, title)
                if not thumbnail_url:
                    flash('Không thể tải lên ảnh thumbnail. Sử dụng ảnh mặc định.', 'warning')
                    thumbnail_url = '/static/images/default-thumbnail.png'
            else:
                # Sử dụng thumbnail mặc định
                thumbnail_url = '/static/images/default-thumbnail.png'

            # Generate a unique ID for this upload
            upload_id = str(uuid.uuid4())
            
            # Read the file content
            file_content = file.read()
            filename = secure_filename(file.filename)
            
            # Create a temporary entry in Firestore for this upload
            _, doc_ref = db.collection('files').add({
                'title': title,
                'author': current_user.name,
                'author_id': current_user.id,
                'file_type': filename.rsplit('.', 1)[1].lower(),
                'file_size': len(file_content),
                'thumbnail_url': thumbnail_url,
                'upload_id': upload_id,
                'upload_status': 'pending',
                'upload_date': datetime.utcnow().isoformat(),
                'approve': False, 
                'visibility': False 
            })
            
            if not isinstance(doc_ref, firestore.DocumentReference):
                raise ValueError(f"doc_ref không phải là DocumentReference, mà là {type(doc_ref)}")
            doc_id = doc_ref.id
            
            # Initialize progress tracking
            upload_progress[upload_id] = {
                'status': 'starting', 
                'progress': 0, 
                'filename': filename,
                'title': title
            }
            
            # Store upload ID in session
            if 'uploads' not in session:
                session['uploads'] = []
            session['uploads'].append(upload_id)
            session.modified = True
            
            # Start background thread for uploading
            upload_thread = threading.Thread(
                target=background_upload_task,
                args=(upload_id, file_content, filename, title, description, tags, 
                      thumbnail_url, current_user.id, current_user.name, 
                      current_user.email, current_user.profile_pic, doc_id)
            )
            upload_thread.daemon = True
            upload_thread.start()

            flash('Tải lên đã bắt đầu và sẽ tiếp tục trong nền!', 'success')
            return redirect(url_for('user_profile.profile', _anchor='uploads'))

        except Exception as e:
            flash(f'Đã xảy ra lỗi: {str(e)}', 'error')
            return redirect(request.url)

    return render_template('upload.html', all_tags=all_tags)


@upload_bp.route('/upload_progress/<upload_id>', methods=['GET'])
@login_required
# @limiter.limit("60 per minute")
def get_upload_progress(upload_id):
    """API endpoint để lấy tiến độ tải lên"""
    # Check in-memory progress first
    if upload_id in upload_progress:
        return jsonify(upload_progress[upload_id])
    
    # If not in memory and marked as completed in session, return completed status
    if 'completed_uploads' in session and upload_id in session['completed_uploads']:
        return jsonify({
            'status': 'completed',
            'progress': 100
        })
            
    # Only check Firestore if we don't know the status
    try:
        uploads = db.collection('files').where('upload_id', '==', upload_id).limit(1).stream()
        for doc in uploads:
            data = doc.to_dict()
            if data.get('upload_status') == 'completed':
                # Store in session to avoid future Firestore queries
                if 'completed_uploads' not in session:
                    session['completed_uploads'] = []
                if upload_id not in session['completed_uploads']:
                    session['completed_uploads'].append(upload_id)
                    session.modified = True
                
                return jsonify({
                    'status': 'completed',
                    'progress': 100
                })
    except Exception as e:
        print(f"Error checking Firestore for upload status: {e}")
        
    return jsonify({'status': 'unknown', 'progress': 0}), 404