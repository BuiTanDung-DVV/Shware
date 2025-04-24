import os
import io
import math
from flask import Blueprint, request, redirect, render_template, flash, url_for
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
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


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def format_filesize(size_bytes):
    """Converts a size in bytes to a human-readable string in KB, MB, or GB."""
    if size_bytes is None or not isinstance(size_bytes, (int, float)) or size_bytes < 0:
        return "N/A"
    if size_bytes == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"


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


@upload_bp.route('/upload_files', methods=['GET', 'POST'])
@login_required
def upload_file():
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

            # 2. Upload file chính lên Google Drive
            filename = secure_filename(file.filename)
            file_content = file.read()
            file_size = len(file_content)
            file.seek(0)

            file_metadata = {
                'name': filename,
                'parents': [FOLDER_ID]
            }
            media = MediaIoBaseUpload(io.BytesIO(file_content), mimetype='application/octet-stream')
            uploaded_file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink'
            ).execute()

            # 3. Lưu thông tin vào Firestore - luôn sử dụng tên người dùng hiện tại
            db.collection('files').add({
                'title': title,
                'author': current_user.name,  # Luôn sử dụng tên người dùng hiện tại
                'email': current_user.email,
                'profile_pic': current_user.profile_pic,
                'description': description,
                'tags': tags,  # Danh sách các tag đã được chọn
                'file_type': filename.rsplit('.', 1)[1].lower(),
                'file_size': file_size,
                'upload_date': datetime.utcnow().isoformat(),
                'download_url': uploaded_file.get('webViewLink'),
                'drive_file_id': uploaded_file.get('id'),
                'thumbnail_url': thumbnail_url,  # Thêm URL thumbnail,
                'avg_rating': 0, 
                'total_reviews': 0,  
                'total_rating_sum': 0  
            })

            flash('Tệp đã được tải lên thành công!', 'success')
            return redirect(url_for('files.list_files'))

        except Exception as e:
            flash(f'Đã xảy ra lỗi: {str(e)}', 'error')
            return redirect(request.url)

    return render_template('upload.html')