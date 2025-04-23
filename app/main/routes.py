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
        # Lấy 5 tệp mới nhất cho slider
        latest_files_docs = db.collection('files') \
            .order_by('upload_date', direction=firestore.Query.DESCENDING) \
            .limit(5) \
            .stream()
        latest_files = []
        for doc in latest_files_docs:
            data = doc.to_dict()
            latest_files.append({
                'title': data.get('title'),
                'description': data.get('description'),
                'download_url': data.get('download_url'),
                'upload_date': data.get('upload_date'),
                'thumbnail_url': data.get('thumbnail_url', 'https://via.placeholder.com/300') # Thêm thumbnail nếu có
            })

        # Lấy tất cả các tệp để phân loại
        all_files_docs = db.collection('files').stream()
        categorized_files = {}
        for doc in all_files_docs:
            data = doc.to_dict()
            category = data.get('category', 'Uncategorized') # Giả sử có trường 'category'
            if category not in categorized_files:
                categorized_files[category] = []
            categorized_files[category].append({
                'title': data.get('title'),
                'description': data.get('description'),
                'download_url': data.get('download_url')
            })

        # Lấy danh sách tệp đã phân trang (vẫn giữ logic phân trang của bạn)
        page = request.args.get('page', 1, type=int)
        per_page = 5
        files = []
        paginated_docs = db.collection('files') \
            .order_by('upload_date', direction=firestore.Query.DESCENDING) \
            .offset((page - 1) * per_page) \
            .limit(per_page) \
            .stream()
        for doc in paginated_docs:
            data = doc.to_dict()
            files.append({
                'title': data.get('title'),
                'description': data.get('description'),
                'tags': ', '.join(data.get('tags', [])),
                'download_url': data.get('download_url')
            })
        total_files = list(db.collection('files').get())
        total_pages = (len(total_files) + per_page - 1) // per_page

        return render_template('home.html',
                               latest_files=latest_files,
                               categorized_files=categorized_files,
                               files=files,
                               page=page,
                               total_pages=total_pages)

    except Exception as e:
        flash(f'Lỗi khi tải dữ liệu trang chủ: {str(e)}', 'error')
        return render_template('home.html', latest_files=[], categorized_files={}, files=[], page=1, total_pages=1)
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
