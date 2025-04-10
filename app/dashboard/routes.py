from flask import render_template, session, redirect, url_for, flash, Blueprint
from firebase_admin import firestore

dashboard_bp = Blueprint('dashboard', __name__)
db = firestore.client()

@dashboard_bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Vui lòng đăng nhập để truy cập trang cá nhân.', 'warning')
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    user_email = session.get('user_email')  # Giả sử bạn lưu email vào session khi đăng nhập
    created_at = session.get('created_at')  # Ngày tạo tài khoản

    # Lấy dữ liệu hồ sơ từ Firestore
    profile_ref = db.collection('profiles').document(user_id)
    doc = profile_ref.get()
    profile = doc.to_dict() if doc.exists else None

    user = {
        'email': user_email,
        'created_at': created_at,
        'id': user_id
    }

    return render_template('dashboard.html', user=user, profile=profile)
