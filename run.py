from flask import session
from app import create_app, db


app = create_app()

if __name__ == '__main__':
    print('nah')
    with app.app_context():
        db.create_all()
    app.run(debug=True)
