from flask import Blueprint, render_template, abort
from firebase_admin import firestore

post_bp = Blueprint('post', __name__)

db = firestore.client()

@post_bp.route('/view/<post_id>')
def view_post(post_id):
    post_ref = db.collection('posts').document(post_id)
    post = post_ref.get()
    
    if post.exists:
        post_data = post.to_dict()
        return render_template('view_post.html', post=post_data)
    else:
        abort(404, description="Bài viết không tồn tại")
