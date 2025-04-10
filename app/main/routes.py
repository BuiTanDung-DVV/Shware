from flask import render_template, flash, Blueprint
from flask_login import current_user  # Thêm dòng này

import firebase_admin
from firebase_admin import credentials, firestore

main_bp = Blueprint('main', __name__)

if not firebase_admin._apps:
    cred = credentials.Certificate('serviceAccountKey.json')
    firebase_admin.initialize_app(cred)
db = firestore.client()

@main_bp.route('/')
def home():
    try:
        files = []
        docs = db.collection('files').order_by('upload_date', direction=firestore.Query.DESCENDING).stream()
        for doc in docs:
            data = doc.to_dict()
            files.append({
                'title': data.get('title'),
                'author': data.get('author'),
                'email': data.get('email'),
                'profile_pic': data.get('profile_pic'),
                'description': data.get('description'),
                'file_type': data.get('file_type'),
                'file_size': data.get('file_size'),
                'tags': ', '.join(data.get('tags', [])),
                'upload_date': data.get('upload_date'),
                'download_url': data.get('download_url')
            })
    except Exception as e:
        flash(f'Lỗi khi tải danh sách tệp: {str(e)}', 'error')
        files = []

    return render_template('home.html', files=files)
