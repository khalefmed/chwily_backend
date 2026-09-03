"""Helpers d'envoi de notifications push (FCM via Firebase Admin).

Extraits de views.py pour être réutilisables par les services de livraison
sans créer d'import circulaire.
"""
from firebase_admin import messaging
from firebase_admin._messaging_utils import UnregisteredError

from ..firebase_init import *  # noqa: F401,F403  (initialise l'app Firebase)
from ..models import User


def send_notification(title, body, token, data=None):
    if not token:
        return None

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in (data or {}).items()},
        token=token,
    )

    try:
        return messaging.send(message)
    except UnregisteredError:
        return None
    except Exception:
        return None


def send_notifications_to_admins(title, body):
    for admin in User.objects.filter(type__in=['admin', 'super_admin']):
        send_notification(title, body, admin.fcm_token)
