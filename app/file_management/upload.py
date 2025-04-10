import os
import io
from flask import Blueprint, request, redirect, render_template, flash, url_for, session
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
SERVICE_ACCOUNT_FILE = os.getenv('ADMIN_GG_DRIVER_SDK_PATH', 'google_drive_admin_sdk.json')
FOLDER_ID = os.getenv('GGDRIVE_FOLDER_ID', '1EnA9Azfv50z7xKllU1Gw4-5r8_Ngys2s')
ALLOWED_EXTENSIONS = {'zip', 'rar'}

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
service = build('drive', 'v3', credentials=creds)

# Firebase Setup
if not firebase_admin._apps:
    firebase_cred = credentials.Certificate(os.getenv('ADMIN_SDK_PATH', 'serviceAccountKey.json'))
    firebase_admin.initialize_app(firebase_cred)
db = firestore.client()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@upload_bp.route('/', methods=['GET', 'POST'])
def upload_file():
    if 'user' not in session:
        flash('Vui lòng đăng nhập trước khi tải lên!')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        file = request.files.get('file')
        title = request.form.get('title')
        author = request.form.get('author')
        description = request.form.get('description')
        tags = request.form.get('tags')

        if not file or not title or not author or not description or not tags:
            flash('Vui lòng điền đầy đủ thông tin và chọn tệp hợp lệ!')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)

            # Đọc kích thước và reset con trỏ
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

            download_url = uploaded_file.get('webViewLink')
            drive_file_id = uploaded_file.get('id')
            file_type = filename.rsplit('.', 1)[1].lower()

            user = session.get('user')

            db.collection('files').add({
                'title': title,
                'author': user['name'] if user else author,
                'email': user.get('email', '') if user else '',
                'profile_pic': user.get('profile_pic', '') if user else '',
                'description': description,
                'tags': [tag.strip() for tag in tags.split(',')],
                'file_type': file_type,
                'file_size': file_size,
                'upload_date': datetime.utcnow().isoformat(),
                'download_url': download_url,
                'drive_file_id': drive_file_id

            })

            flash('Tệp đã được tải lên thành công!')
            return redirect(url_for('files.list_files'))
        else:
            flash('Chỉ cho phép tải lên các file có định dạng .zip hoặc .rar')
            return redirect(request.url)

    return render_template('upload.html')
