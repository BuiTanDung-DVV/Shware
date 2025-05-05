from flask import Blueprint, render_template, abort
from firebase_admin import firestore

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
            posts.append(data)

        return render_template('posts.html', posts=posts)

    except Exception as e:
        print("❌ Lỗi khi lấy danh sách bài viết:", e)
        return render_template('posts.html', posts=[])

@post_bp.route('/view/<post_id>')
def view_post(post_id):
    post_ref = db.collection('posts').document(post_id)
    post = post_ref.get()

    if post.exists:
        post_data = post.to_dict()
        return render_template('view_post.html', post=post_data)
    else:
        abort(404, description="Bài viết không tồn tại")
