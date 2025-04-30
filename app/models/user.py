from flask_login import UserMixin
from firebase_admin import firestore
from datetime import datetime

class User(UserMixin):
    def __init__(self, id_, name, email, profile_pic, role='user', subscription_type='free', 
                 subscription_status='inactive', subscription_start_date=None, subscription_end_date=None):
        self.id = id_
        self.name = name
        self.email = email
        self.profile_pic = profile_pic
        self.role = role
        self.subscription_type = subscription_type
        self.subscription_status = subscription_status
        self.subscription_start_date = subscription_start_date
        self.subscription_end_date = subscription_end_date

    @staticmethod
    def get(user_id):
        try:
            firestore_db = firestore.client()
            user_doc = firestore_db.collection('users').document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                return User(
                    id_=user_id,
                    name=user_data.get('name', ''),
                    email=user_data.get('email', ''),
                    profile_pic=user_data.get('profile_pic', ''),
                    role=user_data.get('role', 'user'),
                    subscription_type=user_data.get('subscription_type', 'free'),
                    subscription_status=user_data.get('subscription_status', 'inactive'),
                    subscription_start_date=user_data.get('subscription_start_date'),
                    subscription_end_date=user_data.get('subscription_end_date')
                )
            return None
        except Exception as e:
            print(f"Error getting user from Firestore: {e}")
            return None