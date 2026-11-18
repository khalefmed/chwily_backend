"""Récompense fidélité au passage d'une commande à `delivered`, quel que soit
le chemin (app admin, callback JEMLI, admin Django) — voir services/pricing.py."""
import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Commande
from .services.notifications import send_notification
from .services.pricing import grant_loyalty_rewards

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Commande)
def reward_delivered_commande(sender, instance, **kwargs):
    if instance.status != 'delivered':
        return
    try:
        granted = grant_loyalty_rewards(instance)
    except Exception:
        logger.exception('Récompense fidélité non versée pour %s', instance.code)
        return
    if granted:
        transaction.on_commit(lambda: _notify_reward(instance))


def _notify_reward(commande):
    from .models import AppConfiguration
    amount = int(AppConfiguration.current().loyalty_reward_amount)
    user = commande.user
    if user.default_lang == 'ar':
        title, body = 'مكافأة الوفاء 🎁', f'ربحت {amount} أوقية ستُخصم من طلبك القادم. شكرًا لوفائك!'
    else:
        title, body = 'Récompense fidélité 🎁', f'Vous avez gagné {amount} MRU, déduits de votre prochaine commande. Merci !'
    try:
        send_notification(title, body, user.fcm_token)
    except Exception:
        logger.exception('Notification fidélité non envoyée à %s', user.pk)
