import os
from dotenv import load_dotenv
from google.oauth2 import service_account

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY') or 'your-secret-key'
    drive_sdk_path = os.getenv("ADMIN_SDK_PATH")
    credentials = service_account.Credentials.from_service_account_file(drive_sdk_path)
    FIREBASE_CONFIG = {
        "apiKey": os.getenv('API_KEY'),
        "authDomain": os.getenv('AUTH_DOMAIN'),
        "databaseURL": os.getenv('FIREBASE_DATABASE_URL'),
        "projectId": os.getenv('PROJECT_ID'),
        "storageBucket": os.getenv('STORAGE_BUCKET'),
        "messagingSenderId": os.getenv('MESSAGING_SENDER_ID'),
        "appId": os.getenv('APP_ID'),
        "measurementId": os.getenv('MEASUREMENT_ID')
    }

    if not FIREBASE_CONFIG['databaseURL']:
        raise ValueError("FIREBASE_DATABASE_URL is not set in the .env file")
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
    FIREBASE_ADMIN_SDK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'serviceAccountKey.json')

    # PayOS Configuration
    PAYOS_CLIENT_ID = os.getenv('PAYOS_CLIENT_ID')
    PAYOS_API_KEY = os.getenv('PAYOS_API_KEY')
    PAYOS_CHECKSUM_KEY = os.getenv('PAYOS_CHECKSUM_KEY')
    PAYOS_API_URL = "https://api-merchant.payos.vn"
