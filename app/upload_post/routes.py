import os
import io
from flask import Blueprint, request, render_template, flash, redirect, url_for, jsonify, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import cloudinary
import cloudinary.uploader
import cloudinary.api
import uuid
from google.cloud.firestore import Increment

post_bp = Blueprint('post', __name__)

# Google Drive setup
SCOPES = ['https://www.googleapis.com/auth/drive']
FOLDER_ID = os.getenv('GGDRIVE_FOLDER_ID')
creds = Credentials.from_service_account_file(os.getenv('ADMIN_SDK_PATH'), scopes=SCOPES)
service = build('drive', 'v3', credentials=creds)

# Firebase setup
if not firebase_admin._apps:
    cred = credentials.Certificate(os.getenv('ADMIN_SDK_PATH'))
    firebase_admin.initialize_app(cred)
db = firestore.client()

ALLOWED_IMG_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Blog categories
BLOG_CATEGORIES = [
    'Tutorials',
    'News',
    'Technology',
    'Programming',
    'Design',
    'Other'
]


def allowed_ext(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set


def upload_to_drive(file_stream, filename):
    file_metadata = {'name': filename, 'parents': [FOLDER_ID]}
    media = MediaIoBaseUpload(file_stream, mimetype='application/octet-stream')
    uploaded = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    return uploaded['id'], uploaded['webViewLink']


def upload_to_cloudinary(file):
    if file and allowed_ext(file.filename, ALLOWED_IMG_EXT):
        try:
            upload_result = cloudinary.uploader.upload(file)
            return upload_result['secure_url']
        except Exception as e:
            flash(f'Error uploading image: {str(e)}', 'error')
    return None

def generate_slug(title):
    """Generate a URL-friendly slug from a title"""
    # Replace special characters and convert to lowercase
    import re
    import unicodedata

    # Normalize unicode characters
    slug = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode('ascii')
    # Convert to lowercase and replace spaces with hyphens
    slug = re.sub(r'[^\w\s-]', '', slug.lower())
    slug = re.sub(r'[\s_-]+', '-', slug)
    slug = re.sub(r'^-+|-+$', '', slug)

    # Add unique identifier
    slug = slug + "-" + uuid.uuid4().hex[:6]
    return slug


@post_bp.route('/upload_post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        description = request.form.get('description')
        category = request.form.get('category', 'Other')
        status = request.form.get('status', 'published')  # Default to published

        thumbnail_file = request.files.get('thumbnail')

        if not title or not content or not description:
            flash('Vui lòng điền đầy đủ các trường bắt buộc!', 'error')
            return redirect(request.url)

        # Upload ảnh thumbnail nếu có
        thumbnail_url = ''
        if thumbnail_file and thumbnail_file.filename:
            # Add file size validation
            if len(thumbnail_file.read()) > 5 * 1024 * 1024:  # 5MB limit
                flash('Kích thước ảnh vượt quá giới hạn cho phép (5MB)', 'error')
                return redirect(request.url)

            # Reset file pointer after reading for size check
            thumbnail_file.seek(0)
            thumbnail_url = upload_to_cloudinary(thumbnail_file)

        # Generate a slug from title
        slug = generate_slug(title)

        # Lưu thông tin bài viết vào Firestore
        post_ref = db.collection('posts').add({
            'title': title,
            'content': content,
            'description': description,
            'category': category,
            'slug': slug,
            'thumbnail_url': thumbnail_url,
            'author': current_user.name,
            'author_id': current_user.id,
            'email': current_user.email,
            'profile_pic': current_user.profile_pic,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'view_count': 0,
            'comments_count': 0,
            'likes': 0,
            'featured': False,
            'status': status  # Use the status from the form
        })

        if status == 'draft':
            flash('Bài viết đã được lưu nháp!', 'success')
            return redirect(url_for('post.my_posts'))
        else:
            flash('Bài viết đã được đăng thành công!', 'success')
            return redirect(url_for('post.view_post', slug=slug))

    return render_template('upload_post.html', categories=BLOG_CATEGORIES)


@post_bp.route('/posts')
def list_posts():
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 9  # Show exactly 9 posts per page

    try:
        category = request.args.get('category', '')

        # Base query
        query = db.collection('posts').where('status', '==', 'published')

        # Apply category filter if provided
        if category:
            query = query.where('category', '==', category)

        query = query.order_by('created_at', direction=firestore.Query.DESCENDING)

        # Get all documents (needed to calculate total for pagination)
        all_docs = list(query.stream())
        total_posts = len(all_docs)
        total_pages = (total_posts + per_page - 1) // per_page  # Ceiling division

        # Get posts for current page
        start_idx = (page - 1) * per_page
        end_idx = min(start_idx + per_page, total_posts)
        page_docs = all_docs[start_idx:end_idx]

        posts = []
        for doc in page_docs:
            data = doc.to_dict()
            data['id'] = doc.id
            # Ensure each post has a slug
            if 'slug' not in data or not data['slug']:
                data['slug'] = generate_slug(data.get('title', 'untitled'))
                # Update slug in database
                db.collection('posts').document(doc.id).update({'slug': data['slug']})

            # Format created_at for display
            if 'created_at' in data and data['created_at']:
                try:
                    date = datetime.fromisoformat(data['created_at'])
                    data['formatted_date'] = date.strftime('%d/%m/%Y')
                except (ValueError, TypeError):
                    data['formatted_date'] = 'N/A'
            posts.append(data)

        # Get list of all categories with counts
        categories = []
        category_counts = {}
        for doc in all_docs:
            post_data = doc.to_dict()
            cat = post_data.get('category', 'Other')
            if cat in category_counts:
                category_counts[cat] += 1
            else:
                category_counts[cat] = 1

        for cat in BLOG_CATEGORIES:
            categories.append({
                'name': cat,
                'count': category_counts.get(cat, 0)
            })

        # Get featured posts
        featured_posts = [doc.to_dict() for doc in all_docs if doc.to_dict().get('featured', False)][:3]
        for post in featured_posts:
            post['id'] = doc.id

        return render_template('posts.html',
                               posts=posts,
                               categories=categories,
                               featured_posts=featured_posts,
                               selected_category=category,
                               page=page,
                               total_pages=total_pages)
    except Exception as e:
        flash(f'Không thể tải danh sách bài viết: {str(e)}', 'error')
        return render_template('posts.html', posts=[], categories=BLOG_CATEGORIES, page=1, total_pages=1)

@post_bp.route('/post/<slug>')
def view_post(slug):
    try:
        # Query post by slug
        posts = db.collection('posts').where('slug', '==', slug).limit(1).stream()
        post = None
        post_id = None

        for doc in posts:
            post = doc.to_dict()
            post_id = doc.id
            break

        if not post:
            flash('Bài viết không tồn tại.', 'error')
            return redirect(url_for('post.list_posts'))

        # Format date
        if 'created_at' in post and post['created_at']:
            try:
                date = datetime.fromisoformat(post['created_at'])
                post['formatted_date'] = date.strftime('%d/%m/%Y')
            except (ValueError, TypeError):
                post['formatted_date'] = 'N/A'

        # Increment view count
        db.collection('posts').document(post_id).update({
            'view_count': Increment(1)
        })

        # Fetch related posts with same category (limit 3)
        related_posts = []
        if post.get('category'):
            related_query = db.collection('posts').where('category', '==', post['category']).where('slug', '!=',
                                                                                                   slug).limit(3)
            for doc in related_query.stream():
                related_post = doc.to_dict()
                related_post['id'] = doc.id
                related_posts.append(related_post)

        # Fetch comments for this post
        comments = []
        comment_docs = db.collection('posts').document(post_id).collection('comments').order_by('created_at').stream()
        for doc in comment_docs:
            comment = doc.to_dict()
            comment['id'] = doc.id
            if 'created_at' in comment and comment['created_at']:
                try:
                    date = datetime.fromisoformat(comment['created_at'])
                    comment['formatted_date'] = date.strftime('%d/%m/%Y %H:%M')
                except (ValueError, TypeError):
                    comment['formatted_date'] = 'N/A'
            comments.append(comment)

        return render_template('view_post.html',
                               post=post,
                               post_id=post_id,
                               related_posts=related_posts,
                               comments=comments,
                               now=datetime.now())
    except Exception as e:
        flash(f'Error loading post: {str(e)}', 'error')
        return redirect(url_for('post.list_posts'))


@post_bp.route('/edit_post/<doc_id>', methods=['GET', 'POST'])
@login_required
def edit_post(doc_id):
    post_ref = db.collection('posts').document(doc_id)
    post = post_ref.get()
    if not post.exists:
        flash('Bài viết không tồn tại.', 'error')
        return redirect(url_for('post.list_posts'))

    post_data = post.to_dict()

    # Check if user is author or admin
    if current_user.email != post_data.get('email') and current_user.role != 'admin':
        flash('Bạn không có quyền chỉnh sửa bài viết này.', 'error')
        return redirect(url_for('post.list_posts'))

    if request.method == 'POST':
        new_title = request.form.get('title')
        new_description = request.form.get('description')
        new_content = request.form.get('content')
        new_category = request.form.get('category', post_data.get('category', 'Other'))
        thumbnail_file = request.files.get('thumbnail')
        attachment_file = request.files.get('attachment')

        updated_data = {
            'title': new_title,
            'description': new_description,
            'content': new_content,
            'category': new_category,
            'updated_at': datetime.utcnow().isoformat()
        }

        # Update thumbnail if provided
        if thumbnail_file and thumbnail_file.filename:
            thumbnail_url = upload_to_cloudinary(thumbnail_file)
            if thumbnail_url:
                updated_data['thumbnail_url'] = thumbnail_url
        try:
            post_ref.update(updated_data)
            flash('Cập nhật bài viết thành công!', 'success')
            return redirect(url_for('post.view_post', slug=post_data.get('slug')))
        except Exception as e:
            flash(f'Không thể cập nhật bài viết: {e}', 'error')
            return redirect(request.url)

    return render_template('edit_post.html', post=post_data, post_id=doc_id, categories=BLOG_CATEGORIES)


@post_bp.route('/delete_post/<doc_id>', methods=['POST'])
@login_required
def delete_post(doc_id):
    try:
        post_ref = db.collection('posts').document(doc_id)
        post = post_ref.get()

        if not post.exists:
            flash('Bài viết không tồn tại.', 'error')
            return redirect(url_for('post.list_posts'))

        post_data = post.to_dict()

        # Check if user is author or admin
        if current_user.email != post_data.get('email') and current_user.role != 'admin':
            flash('Bạn không có quyền xóa bài viết này.', 'error')
            return redirect(url_for('post.list_posts'))

        # Delete comments subcollection first
        comments = post_ref.collection('comments').stream()
        for comment in comments:
            comment.reference.delete()

        # Then delete the post
        post_ref.delete()
        flash('Bài viết đã được xóa thành công!', 'success')
        return redirect(url_for('post.list_posts'))
    except Exception as e:
        flash(f'Lỗi khi xóa bài viết: {str(e)}', 'error')
        return redirect(url_for('post.list_posts'))


@post_bp.route('/add_comment/<post_id>', methods=['POST'])
@login_required
def add_comment(post_id):
    try:
        post_ref = db.collection('posts').document(post_id)
        post = post_ref.get()

        if not post.exists:
            return jsonify({'success': False, 'message': 'Bài viết không tồn tại'}), 404

        comment_content = request.form.get('content')

        if not comment_content or len(comment_content.strip()) < 2:
            return jsonify({'success': False, 'message': 'Nội dung bình luận quá ngắn'}), 400

        # Add comment to subcollection
        comment_ref = post_ref.collection('comments').add({
            'content': comment_content,
            'author_name': current_user.name,
            'author_id': current_user.id,
            'author_email': current_user.email,
            'author_profile_pic': current_user.profile_pic,
            'created_at': datetime.utcnow().isoformat()
        })

        # Update comment count
        post_ref.update({
            'comments_count': Increment(1)
        })

        # Format date for response
        formatted_date = datetime.now().strftime('%d/%m/%Y %H:%M')

        return jsonify({
            'success': True,
            'message': 'Bình luận đã được thêm',
            'comment_id': comment_ref[1].id,
            'author_name': current_user.name,
            'author_profile_pic': current_user.profile_pic,
            'formatted_date': formatted_date,
            'content': comment_content
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'}), 500


@post_bp.route('/delete_comment/<post_id>/<comment_id>', methods=['POST'])
@login_required
def delete_comment(post_id, comment_id):
    try:
        post_ref = db.collection('posts').document(post_id)
        comment_ref = post_ref.collection('comments').document(comment_id)
        comment = comment_ref.get()

        if not comment.exists:
            return jsonify({'success': False, 'message': 'Bình luận không tồn tại'}), 404

        comment_data = comment.to_dict()

        # Check if user is comment author or admin
        if current_user.id != comment_data.get('author_id') and current_user.role != 'admin':
            return jsonify({'success': False, 'message': 'Bạn không có quyền xóa bình luận này'}), 403

        # Delete comment
        comment_ref.delete()

        # Update comment count
        post_ref.update({
            'comments_count': Increment(-1)
        })

        return jsonify({'success': True, 'message': 'Bình luận đã được xóa'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'}), 500


@post_bp.route('/like_post/<post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    try:
        post_ref = db.collection('posts').document(post_id)
        post = post_ref.get()

        if not post.exists:
            return jsonify({'success': False, 'message': 'Bài viết không tồn tại'}), 404

        # Check if user already liked this post
        like_ref = db.collection('likes').where('post_id', '==', post_id).where('user_id', '==', current_user.id).limit(
            1)
        likes = list(like_ref.stream())

        if likes:
            # User already liked this post, so unlike it
            likes[0].reference.delete()
            post_ref.update({
                'likes': Increment(-1)
            })
            return jsonify({'success': True, 'liked': False, 'message': 'Đã bỏ thích bài viết'})
        else:
            # User hasn't liked this post yet, so like it
            db.collection('likes').add({
                'post_id': post_id,
                'user_id': current_user.id,
                'created_at': datetime.utcnow().isoformat()
            })
            post_ref.update({
                'likes': Increment(1)
            })
            return jsonify({'success': True, 'liked': True, 'message': 'Đã thích bài viết'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'}), 500


@post_bp.route('/check_like/<post_id>', methods=['GET'])
@login_required
def check_like(post_id):
    try:
        # Check if user already liked this post
        like_ref = db.collection('likes').where('post_id', '==', post_id).where('user_id', '==', current_user.id).limit(
            1)
        likes = list(like_ref.stream())

        if likes:
            return jsonify({'success': True, 'liked': True})
        else:
            return jsonify({'success': True, 'liked': False})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'}), 500


@post_bp.route('/featured_posts')
def featured_posts():
    try:
        featured = []
        docs = db.collection('posts').where('featured', '==', True).limit(4).stream()

        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            featured.append(data)

        return jsonify({'success': True, 'posts': featured})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'}), 500


@post_bp.route('/my_posts')
@login_required
def my_posts():
    try:
        posts = []
        docs = db.collection('posts').where('author_id', '==', current_user.id).order_by('created_at',
                                                                                         direction=firestore.Query.DESCENDING).stream()

        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            # Add the slug to each post to ensure we have it available for URL generation
            if 'created_at' in data and data['created_at']:
                try:
                    date = datetime.fromisoformat(data['created_at'])
                    data['formatted_date'] = date.strftime('%d/%m/%Y')
                except (ValueError, TypeError):
                    data['formatted_date'] = 'N/A'
            posts.append(data)

        return render_template('my_posts.html', posts=posts)
    except Exception as e:
        flash(f'Không thể tải danh sách bài viết của bạn: {str(e)}', 'error')
        return render_template('my_posts.html', posts=[])