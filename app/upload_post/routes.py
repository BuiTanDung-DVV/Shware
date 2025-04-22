import os
import io
from flask import Blueprint, request, render_template, flash, redirect, url_for
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


post_bp = Blueprint('post', __name__)

# Google Drive setup
SCOPES = ['https://www.googleapis.com/auth/drive']
FOLDER_ID = os.getenv('GGDRIVE_FOLDER_ID')
creds = Credentials.from_service_account_file(os.getenv('ADMIN_SDK_PATH'), scopes=SCOPES)
service = build('drive', 'v3', credentials=creds)

# Firebase setup
if not firebase_admin._apps:
    cred = credentials.Certificate(os.getenv('ADMIN_SDK_PATH'))
    firebase_admin.initialize_app(cred)
db = firestore.client()

ALLOWED_FILE_EXT = {'zip', 'rar'}
ALLOWED_IMG_EXT = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_ext(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set

def upload_to_drive(file_stream, filename):
    file_metadata = {'name': filename, 'parents': [FOLDER_ID]}
    media = MediaIoBaseUpload(file_stream, mimetype='application/octet-stream')
    uploaded = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    return uploaded['id'], uploaded['webViewLink']

@post_bp.route('/upload_post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        description = request.form.get('description')
        tags = request.form.get('tags', '')
        tags_list = [tag.strip() for tag in tags.split(',') if tag.strip()]

        thumbnail_file = request.files.get('thumbnail')
        attachment_file = request.files.get('attachment')

        if not title or not content or not description:
            flash('Vui lòng điền đầy đủ các trường bắt buộc!', 'error')
            return redirect(request.url)

        # Upload ảnh thumbnail nếu có
        thumbnail_url = ''
        if thumbnail_file and allowed_ext(thumbnail_file.filename, ALLOWED_IMG_EXT):
        filename = secure_filename(thumbnail_file.filename)
        thumb_id, thumb_link = upload_to_drive(thumbnail_file.stream, filename)
        thumbnail_url = thumb_link
        # Upload ảnh thumbnail lên Cloudinary
        upload_result = cloudinary.uploader.upload(thumbnail_file)
        thumbnail_url = upload_result['secure_url']  # Lấy URL an toàn từ Cloudinary

        # Upload file đính kèm nếu có
        file_info = {}
        if attachment_file and allowed_ext(attachment_file.filename, ALLOWED_FILE_EXT):
            filename = secure_filename(attachment_file.filename)
            file_content = attachment_file.read()
            file_size = len(file_content)
            attachment_file.seek(0)
            file_id, file_link = upload_to_drive(io.BytesIO(file_content), filename)

            file_info = {
                'file_name': filename,
                'file_size': file_size,
                'file_type': filename.rsplit('.', 1)[1].lower(),
                'file_url': file_link,
                'drive_file_id': file_id
            }

        # Lưu thông tin bài viết vào Firestore
        db.collection('posts').add({
            'title': title,
            'content': content,
            'description': description,
            'tags': tags_list,
            'thumbnail_url': thumbnail_url,
            'file_info': file_info,
            'author': current_user.name,
            'email': current_user.email,
            'profile_pic': current_user.profile_pic,
            'created_at': datetime.utcnow().isoformat()
        })

        flash('Bài viết đã được đăng thành công!', 'success')
        return redirect(url_for('post.list_posts'))

    return render_template('upload_post.html')

@post_bp.route('/posts')
def list_posts():
    try:
        posts = []
        docs = db.collection('posts').order_by('created_at', direction=firestore.Query.DESCENDING).stream()
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            posts.append(data)
        return render_template('posts.html', posts=posts)
    except Exception as e:
        flash(f'Không thể tải danh sách bài viết: {str(e)}', 'error')
        return render_template('posts.html', posts=[])
        # EDIT POST
@post_bp.route('/edit_post/<doc_id>', methods=['GET', 'POST'])
@login_required
def edit_post(doc_id):
    post_ref = db.collection('posts').document(doc_id)
    post = post_ref.get()
    if not post.exists:
        flash('Bài viết không tồn tại.')
        return redirect(url_for('post.list_posts'))

    post_data = post.to_dict()

    if request.method == 'POST':
        new_title = request.form.get('title')
        new_description = request.form.get('description')
        new_content = request.form.get('content')
        new_tags = [tag.strip() for tag in request.form.get('tags', '').split(',') if tag.strip()]
        image_file = request.files.get('image')

        updated_data = {
            'title': new_title,
            'description': new_description,
            'content': new_content,
            'tags': new_tags
        }

        if image_file and image_file.filename:
        # Upload ảnh mới lên Cloudinary
         upload_result = cloudinary.uploader.upload(image_file)
         updated_data['image_url'] = upload_result['secure_url']  # Lấy URL an toàn từ Cloudinary


        try:
            post_ref.update(updated_data)
            flash('Cập nhật bài viết thành công!')
            return redirect(url_for('post.list_posts'))
        except Exception as e:
            flash(f'Không thể cập nhật bài viết: {e}')
            return redirect(request.url)

    return render_template('edit.html', post=post_data, post_id=doc_id)
