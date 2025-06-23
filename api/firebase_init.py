import os
from firebase_admin import credentials, initialize_app

cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

if not initialize_app._apps:
    cred = credentials.Certificate(cred_path)
    initialize_app(cred)