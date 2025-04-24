import os
from flask import Blueprint, render_template, flash, redirect, url_for, request, abort
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

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

        # Add a placeholder image URL if none exists
        # You might want to store an actual image URL during upload
        file_data.setdefault('image_url', url_for('static', filename='default_placeholder.png')) # Replace with your actual placeholder image

        return render_template('file_detail.html', file=file_data)

    except Exception as e:
        flash(f'Lỗi khi tải chi tiết tệp: {str(e)}', 'error')
        # Redirect to a safe page, like the file list or home
        return redirect(url_for('files.list_files'))
