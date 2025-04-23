from flask import render_template, flash, Blueprint, request  # Add request
from flask_login import current_user

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
        page = request.args.get('page', 1, type=int)
        per_page = 5
        files = []
        docs = db.collection('files') \
            .order_by('upload_date', direction=firestore.Query.DESCENDING) \
            .offset((page - 1) * per_page) \
            .limit(per_page) \
            .stream()
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
        total_files = db.collection('files').get()
        total_pages = (len(total_files) + per_page - 1) // per_page

    except Exception as e:
        flash(f'Lỗi khi tải danh sách tệp: {str(e)}', 'error')
        files = []
        total_pages = 1
    return render_template('home.html', files=files, page=page, total_pages=total_pages)

@main_bp.route('/search')
def search():
    query = request.args.get('q', '').strip()
    results = []
    if not query:
        flash('Vui lòng nhập từ khóa tìm kiếm.', 'warning')
        return render_template('search_results.html', query=query, results=results)

    try:
        query_lower = query.lower()
        all_files_ref = db.collection('files')
        docs = all_files_ref.stream()

        for doc in docs:
            data = doc.to_dict()
            title_match = query_lower in data.get('title', '').lower()
            desc_match = query_lower in data.get('description', '').lower()
            tags_match = any(query_lower in tag.lower() for tag in data.get('tags', []))

            if title_match or desc_match or tags_match:
                results.append({
                    'id': doc.id,
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

        if not results:
            flash(f'Không tìm thấy kết quả nào cho "{query}".', 'info')

    except Exception as e:
        flash(f'Lỗi khi tìm kiếm: {str(e)}', 'error')
        results = []

    return render_template('search_results.html', query=query, results=results)
