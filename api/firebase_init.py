from decouple import config
import firebase_admin
from firebase_admin import credentials, messaging

cred_path = config("GOOGLE_APPLICATION_CREDENTIALS")

if not firebase_admin._apps:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)