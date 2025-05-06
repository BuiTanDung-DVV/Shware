from flask import Blueprint, render_template, request, flash, url_for
from flask_login import current_user
import firebase_admin
from firebase_admin import credentials, firestore

search_bp = Blueprint('search', __name__)

db = firestore.client()

@search_bp.route('/search')
def search():
    query = request.args.get('q', '').strip()
    results = []
    
    # Lấy các tham số lọc
    sort_by = request.args.get('sort_by', 'upload_date')
    sort_direction = request.args.get('sort_direction', 'desc')
    tag_filter = request.args.get('tag')
    file_type_filter = request.args.get('file_type')

    # Danh sách các trường hợp lệ
    valid_sort_fields = ['title', 'author', 'file_type', 'file_size', 'upload_date', 'avg_rating']
    if sort_by not in valid_sort_fields:
        sort_by = 'upload_date'

    valid_directions = ['asc', 'desc']
    if sort_direction not in valid_directions:
        sort_direction = 'desc'

    if not query:
        flash('Vui lòng nhập từ khóa tìm kiếm.', 'warning')
        return render_template('search_results.html', query=query, results=results)

    try:
        # Xây dựng truy vấn cơ bản
        base_query = db.collection('files').where(filter=firestore.FieldFilter('visibility', '==', True))
        
        # Thêm lọc theo tag nếu có
        if tag_filter:
            base_query = base_query.where(filter=firestore.FieldFilter('tags', 'array_contains', tag_filter))
            
        # Thêm lọc theo file_type nếu có
        if file_type_filter:
            base_query = base_query.where(filter=firestore.FieldFilter('file_type', '==', file_type_filter))
            
        # Thêm sắp xếp
        direction = firestore.Query.DESCENDING if sort_direction == 'desc' else firestore.Query.ASCENDING
        docs = base_query.order_by(sort_by, direction=direction).stream()

        query_lower = query.lower()
        for doc in docs:
            data = doc.to_dict()
            # Tìm kiếm trong title, description và tags
            # visible = data.get('visibility', True)
            title_match = query_lower in data.get('title', '').lower()
            desc_match = query_lower in data.get('description', '').lower()
            tags_match = any(query_lower in tag.lower() for tag in data.get('tags', []))

            if (title_match or desc_match or tags_match):
                results.append({
                    'doc_id': doc.id,
                    'title': data.get('title'),
                    'description': data.get('description'),
                    'tags': data.get('tags', []),
                    'file_type': data.get('file_type'),
                    'file_size': data.get('file_size'),
                    'thumbnail_url': data.get('thumbnail_url', url_for('static', filename='default_placeholder.png')),
                    'avg_rating': data.get('avg_rating', 0),
                    'total_reviews': data.get('total_reviews', 0)
                })

        # Lấy file types từ một số lượng giới hạn files
        all_file_types = set()
        type_docs = db.collection('files').limit(100).stream()
        for doc in type_docs:
            data = doc.to_dict()
            all_file_types.add(data.get('file_type'))

        # Lấy tags từ collection tags, sắp xếp theo số lượng references
        all_tags = []
        tags_docs = db.collection('tags').order_by('references', direction=firestore.Query.DESCENDING).stream()
        for doc in tags_docs:
            data = doc.to_dict()
            if data.get('references', 0) > 0:  # Chỉ lấy những tags đang được sử dụng
                all_tags.append(data.get('name'))

        # if not results:
        #     flash(f'Không tìm thấy kết quả nào cho "{query}".', 'info')

    except Exception as e:
        flash(f'Lỗi khi tìm kiếm: {str(e)}', 'error')
        results = []
        all_file_types = set()
        all_tags = []
        sort_by = 'upload_date'
        sort_direction = 'desc'
        tag_filter = None
        file_type_filter = None

    return render_template('search_results.html', 
                         query=query,
                         results=results,
                         sort_by=sort_by,
                         sort_direction=sort_direction,
                         all_file_types=sorted(all_file_types),
                         all_tags=all_tags,
                         current_tag=tag_filter,
                         current_file_type=file_type_filter)