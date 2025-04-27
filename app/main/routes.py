from flask import render_template, flash, Blueprint, request, url_for
from flask_login import current_user
import firebase_admin
from firebase_admin import credentials, firestore
import os

main_bp = Blueprint('main', __name__)

# Khởi tạo Firebase Admin SDK
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
                'doc_id': doc.id,
                'title': data.get('title'),
                'description': data.get('description'),
                'download_url': data.get('download_url'),
                'upload_date': data.get('upload_date'),
                'thumbnail_url': data.get('thumbnail_url', url_for('static', filename='default-thumbnail.png')),
                'file_size': data.get('file_size') 
            })

        # Lấy tag từ parameters nếu có
        selected_tag = request.args.get('tag')
        page = request.args.get('page', 1, type=int)
        per_page = 12

        # Xây dựng query cho files
        files_query = db.collection('files').order_by('upload_date', direction=firestore.Query.DESCENDING)
        if selected_tag:
            files_query = files_query.where(filter=firestore.FieldFilter('tags', 'array_contains', selected_tag))

        # Lấy danh sách files với phân trang
        files = []
        total_count = 0
        docs = files_query.stream()
        for i, doc in enumerate(docs):
            if i >= (page - 1) * per_page and i < page * per_page:
                data = doc.to_dict()
                files.append({
                    'doc_id': doc.id,
                    'title': data.get('title'),
                    'tags': data.get('tags', []),
                    'thumbnail_url': data.get('thumbnail_url', url_for('static', filename='default-thumbnail.png')),
                    'avg_rating': data.get('avg_rating', 0),
                    'total_reviews': data.get('total_reviews', 0)
                })
            total_count += 1

        total_pages = (total_count + per_page - 1) // per_page

        # Lấy tags từ collection tags
        all_tags = []
        try:
            # In ra để debug
            print("Fetching tags from collection...")
            tags_docs = db.collection('tags')\
                         .order_by('references', direction=firestore.Query.DESCENDING)\
                         .stream()
            
            for doc in tags_docs:
                data = doc.to_dict()
                if data.get('references', 0) > 0:  # Chỉ lấy những tags đang được sử dụng
                    print(f"Found tag: {data.get('name')} with {data.get('references')} references")
                    all_tags.append(data.get('name'))
        except Exception as e:
            print(f"Error fetching tags: {e}")
            # Fallback: lấy tags từ files nếu collection tags có vấn đề
            try:
                all_tags_set = set()
                files_for_tags = db.collection('files').stream()
                for doc in files_for_tags:
                    file_tags = doc.to_dict().get('tags', [])
                    all_tags_set.update(file_tags)
                all_tags = sorted(list(all_tags_set))
                print(f"Fallback: Found {len(all_tags)} tags from files")
            except Exception as e:
                print(f"Error in fallback tag fetching: {e}")

        return render_template('home.html',
                            latest_files=latest_files,
                            files=files,
                            all_tags=all_tags,
                            selected_tag=selected_tag,
                            page=page,
                            total_pages=total_pages)

    except Exception as e:
        print(f"Error in home route: {e}")  # In ra lỗi để debug
        flash(f'Lỗi khi tải dữ liệu trang chủ: {str(e)}', 'error')
        return render_template('home.html', 
                            latest_files=[], 
                            files=[], 
                            all_tags=[], 
                            selected_tag=None,
                            page=1, 
                            total_pages=1)
