import firebase_admin
from firebase_admin import credentials, messaging

cred = credentials.Certificate("firebase_admin_sdk.json")
firebase_admin.initialize_app(cred)
