from flask import Blueprint, render_template, abort, current_app
from firebase_admin import firestore

post_bp = Blueprint('post', __name__, template_folder='templates')
db = firestore.client()

@post_bp.route('/list')
def list_posts():
    try:
        posts = db.collection('posts').order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
        post_list = [(doc.id, doc.to_dict()) for doc in posts]
        return render_template('post/posts.html', posts=post_list)
    except Exception as e:
        print("Lỗi khi lấy bài viết:", e)
        return render_template('post/posts.html', posts=[])

@post_bp.route('/view/<post_id>')
def view_post(post_id):
    post_ref = db.collection('posts').document(post_id)
    post = post_ref.get()
    
    if post.exists:
        post_data = post.to_dict()
        return render_template('post/view_post.html', post=post_data)
    else:
        abort(404, description="Bài viết không tồn tại")
