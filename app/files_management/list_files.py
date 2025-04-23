import os
from flask import Blueprint, render_template, flash, redirect, url_for, request
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import firebase_admin
from firebase_admin import credentials, firestore

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
        files = []
        docs = db.collection('files').offset((page - 1) * per_page).limit(per_page).stream()
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
                'tags': ', '.join(data.get('tags', [])),
                'upload_date': data.get('upload_date'),
                'download_url': data.get('download_url'),
                'drive_file_id': data.get('drive_file_id')
            })

        # Get total file count for pagination
        total_files = db.collection('files').get()
        total_pages = (len(total_files) + per_page - 1) // per_page

    except Exception as e:
        flash(f'Không thể tải danh sách tệp: {str(e)}')
        files = []
        total_pages = 1

    return render_template('files.html', files=files, page=page, total_pages=total_pages)

@files_bp.route('/delete/<doc_id>', methods=['POST'])
def delete_file(doc_id):
    try:
        doc_ref = db.collection('files').document(doc_id)
        doc = doc_ref.get()
        if not doc.exists:
            flash('Không tìm thấy tệp để xóa!')
            return redirect(url_for('files.list_files'))

        drive_file_id = doc.to_dict().get('drive_file_id')
        if drive_file_id:
            try:
                service.files().delete(fileId=drive_file_id).execute()
            except Exception as e:
                flash(f'Không thể xóa file trên Google Drive: {str(e)}')

        doc_ref.delete()
        flash('Tệp đã được xóa thành công!')
    except Exception as e:
        flash(f'Không thể xóa tệp: {str(e)}')

    return redirect(url_for('files.list_files'))
