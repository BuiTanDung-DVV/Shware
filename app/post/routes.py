from flask import Blueprint, render_template, abort
from firebase_admin import firestore
from datetime import datetime

post_bp = Blueprint('post', __name__)
db = firestore.client()


@post_bp.route('/posts')
def list_posts():
    try:
        # Lấy danh sách bài viết, sắp xếp theo ngày tạo mới nhất
        posts_ref = db.collection('posts').order_by('created_at', direction=firestore.Query.DESCENDING)
        posts = []

        # Lấy dữ liệu từng bài viết
        docs = posts_ref.stream()
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id  # thêm ID để dùng khi xem chi tiết

            # Chuyển đổi timestamp thành datetime
            if 'created_at' in data:
                data['created_at'] = data['created_at'].to_datetime()
            if 'updated_at' in data:
                data['updated_at'] = data['updated_at'].to_datetime()

            # Lưu giữ datetime object để có thể format trong template
            # Nếu cần string format cho danh sách, thêm trường mới
            if 'created_at' in data:
                data['created_at_formatted'] = data['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            if 'updated_at' in data:
                data['updated_at_formatted'] = data['updated_at'].strftime('%Y-%m-%d %H:%M:%S')

            posts.append(data)

        return render_template('posts.html', posts=posts)

    except Exception as e:
        print("❌ Lỗi khi lấy danh sách bài viết:", e)
        return render_template('posts.html', posts=[])


@post_bp.route('/view/<plug>')
def view_post(post_id):
    try:
        post_ref = db.collection('posts').document(post_id)
        post = post_ref.get()

        if post.exists:
            post_data = post.to_dict()
            post_data['id'] = post.id

            # Chuyển đổi timestamp thành datetime
            if 'created_at' in post_data and hasattr(post_data['created_at'], 'to_datetime'):
                post_data['created_at'] = post_data['created_at'].to_datetime()
            if 'updated_at' in post_data and hasattr(post_data['updated_at'], 'to_datetime'):
                post_data['updated_at'] = post_data['updated_at'].to_datetime()

            return render_template('view_post.html', post=post_data)
        else:
            abort(404, description="Bài viết không tồn tại")
    except Exception as e:
        print("❌ Lỗi khi xem chi tiết bài viết:", e)
        abort(500, description="Lỗi server khi xem bài viết")