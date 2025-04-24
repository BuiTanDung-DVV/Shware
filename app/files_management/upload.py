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

@upload_bp.route('/upload_files', methods=['GET', 'POST'])
@login_required
def upload_file():
    if request.method == 'POST':
        file = request.files.get('file')
        title = request.form.get('title')
        description = request.form.get('description')
        tags = request.form.get('tags')

        if not file or not title or not description or not tags:
            flash('Vui lòng điền đầy đủ thông tin và chọn tệp hợp lệ!')
            return redirect(request.url)

        if file and allowed_file(file.filename):
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

            db.collection('files').add({
                'title': title,
                'author': current_user.name,
                'email': current_user.email,
                'profile_pic': current_user.profile_pic,
                'description': description,
                'tags': [tag.strip() for tag in tags.split(',')],
                'file_type': filename.rsplit('.', 1)[1].lower(),
                'file_size': file_size,
                'upload_date': datetime.utcnow().isoformat(),
                'download_url': uploaded_file.get('webViewLink'),
                'drive_file_id': uploaded_file.get('id')
            })

            flash('Tệp đã được tải lên thành công!')
            return redirect(url_for('files.list_files'))
        else:
            flash('Chỉ cho phép tải lên các file có định dạng .zip hoặc .rar')
            return redirect(request.url)

    return render_template('upload.html')
