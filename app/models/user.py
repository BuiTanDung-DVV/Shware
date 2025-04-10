from flask_login import UserMixin

from . import db

class User(UserMixin, db.Model):
    id = db.Column(db.String(150), primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    profile_pic = db.Column(db.String(200), nullable=True)

    def __init__(self, id_, name, email, profile_pic):
        self.id = id_
        self.name = name
        self.email = email
        self.profile_pic = profile_pic