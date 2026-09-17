"""Orchestration de la livraison via partenaire : résolution du type,
devis, envoi immédiat ou planifié, application des statuts partenaire.
"""
import logging
import uuid

from django.conf import settings
from django.utils import timezone

from ..models import DeliveryType
from .jemli import (
    DeliveryPartnerError,
    JemliClient,
    extract_delivery_ref,
    extract_price,
)
from .notifications import send_notification, send_notifications_to_admins

logger = logging.getLogger(__name__)

# Correspondance statut partenaire -> statut Commande.
# TODO(jemli-doc) : compléter / corriger avec les vrais libellés JEMLI.
JEMLI_STATUS_MAP = {
    'pending': 'looking_for_driver',
    'searching': 'looking_for_driver',
    'looking_for_driver': 'looking_for_driver',
    'assigned': 'driver_assigned',
    'driver_assigned': 'driver_assigned',
    'accepted': 'driver_assigned',
    'picked_up': 'loading',
    'in_transit': 'loading',
    'on_the_way': 'loading',
    'delivering': 'loading',
    'delivered': 'delivered',
    'completed': 'delivered',
    'cancelled': 'rejected',
    'canceled': 'rejected',
    'failed': 'rejected',
}

# Libellés notifiés au client, par langue.
_STATUS_LABELS = {
    'ar': {
        'looking_for_driver': 'جاري البحث عن موصّل',
        'driver_assigned': 'تم تعيين موصّل',
        'loading': 'قيد المعالجة',
        'delivered': 'تم التوصيل',
        'rejected': 'مرفوض',
    },
    'fr': {
        'looking_for_driver': "Recherche d'un livreur",
        'driver_assigned': 'Livreur assigné',
        'loading': 'En cours',
        'delivered': 'Livrée',
        'rejected': 'Rejetée',
    },
}

_CLIENTS = {'jemli': JemliClient}


def client_for(provider):
    cls = _CLIENTS.get(provider.code)
    if cls is None:
        raise DeliveryPartnerError(f'Aucun client pour le provider "{provider.code}".')
    return cls(provider)


def _provider_types_for(commande):
    codes = {
        item.category.type
        for item in commande.items.select_related('category').all()
        if item.category_id
    }
    return list(
        DeliveryType.objects
        .filter(code__in=codes, is_active=True, provider__isnull=False)
        .select_related('provider', 'provider__origin_point')
    )


def resolve_delivery_type(commande):
    """DeliveryType à utiliser pour la commande, ou None (livraison legacy).

    Si un type planifié (mes_plats) est présent, toute la commande est
    livrée avec ce type (donc planifiée).
    """
    types = _provider_types_for(commande)
    if not types:
        return None
    for delivery_type in types:
        if delivery_type.is_scheduled:
            return delivery_type
    return types[0]


def quote_delivery(delivery_type, destination):
    """Renvoie {partner_delivery_fee, delivery_margin, delivery_final_price, raw}."""
    provider = delivery_type.provider
    if provider is None or provider.origin_point is None:
        raise DeliveryPartnerError('Provider ou point de départ non configuré.')

    payload = client_for(provider).compute_pricing(provider.origin_point, destination)
    fee = extract_price(payload)
    margin = delivery_type.delivery_margin or 0
    return {
        'partner_delivery_fee': round(fee, 2),
        'delivery_margin': margin,
        'delivery_final_price': round(fee + margin, 2),
        'raw': payload,
    }


def dispatch_commande(commande, force=False):
    """Appelée quand la commande passe à `paid`. Envoie au partenaire,
    immédiatement ou en planifiant (mes_plats)."""
    delivery_type = commande.delivery_type or resolve_delivery_type(commande)
    if delivery_type is None or delivery_type.provider is None:
        return  # livraison legacy : rien à faire

    if commande.dispatch_status == 'sent' and not force:
        return

    commande.delivery_type = delivery_type
    commande.delivery_provider = delivery_type.provider

    scheduled = (
        delivery_type.is_scheduled
        and commande.delivery_datetime
        and commande.delivery_datetime > timezone.now()
    )
    if scheduled:
        commande.dispatch_status = 'scheduled'
        commande.save(update_fields=['delivery_type', 'delivery_provider', 'dispatch_status'])
        logger.info('Commande %s planifiée pour %s', commande.code, commande.delivery_datetime)
        return

    send_to_partner(commande)


def send_to_partner(commande):
    """Envoi effectif de la commande au partenaire (immédiat ou déclenché
    par le planificateur).

    En mode sandbox (settings.DELIVERY_SANDBOX), la création réelle chez le
    partenaire est simulée : dev et prod partagent pour l'instant les mêmes
    identifiants JEMLI, donc appeler la vraie API depuis un environnement de
    test enverrait un chauffeur réel.
    """
    provider = commande.delivery_provider
    if settings.DELIVERY_SANDBOX:
        ref = f'SANDBOX-{uuid.uuid4().hex[:10]}'
        logger.warning(
            '[SANDBOX] Dispatch simulé pour %s vers %s (aucun appel JEMLI réel, ref=%s)',
            commande.code, provider.name, ref,
        )
    else:
        try:
            response = client_for(provider).create_delivery(commande)
            ref = extract_delivery_ref(response)
        except DeliveryPartnerError as exc:
            commande.dispatch_status = 'failed'
            commande.save(update_fields=['delivery_type', 'delivery_provider', 'dispatch_status'])
            logger.error('Dispatch commande %s échoué : %s', commande.code, exc)
            send_notifications_to_admins(
                'Échec envoi livraison',
                f"La commande {commande.code} n'a pas pu être envoyée à {provider.name}.",
            )
            return False

    commande.partner_delivery_ref = ref
    commande.dispatch_status = 'sent'
    commande.dispatched_at = timezone.now()
    commande.status = 'looking_for_driver'
    commande.save(update_fields=[
        'delivery_type', 'delivery_provider', 'partner_delivery_ref',
        'dispatch_status', 'dispatched_at', 'status',
    ])
    notify_client_status(commande, 'looking_for_driver')
    logger.info('Commande %s envoyée à %s (ref %s)', commande.code, provider.name, ref)
    return True


def notify_client_status(commande, new_status):
    lang = getattr(commande.user, 'default_lang', 'fr') or 'fr'
    labels = _STATUS_LABELS.get(lang, _STATUS_LABELS['fr'])
    label = labels.get(new_status, new_status)
    if lang == 'ar':
        body = f'تم تحديث حالة طلبك {commande.code}: {label}'
    else:
        body = f'Votre commande {commande.code} : {label}'
    send_notification(label, body, commande.user.fcm_token, data={
        'type': 'commande_status', 'commande': commande.code, 'status': new_status,
    })


def apply_partner_status(commande, external_status, driver_phone=None):
    """Applique un statut reçu du partenaire (webhook / polling).
    Retourne le nouveau statut Commande, ou None si inchangé."""
    mapped = JEMLI_STATUS_MAP.get(str(external_status or '').lower().strip())
    fields = []

    if driver_phone and driver_phone != commande.driver_phone:
        commande.driver_phone = driver_phone
        fields.append('driver_phone')

    changed = None
    if mapped and mapped != commande.status:
        commande.status = mapped
        fields.append('status')
        if mapped == 'delivered':
            commande.dispatch_status = 'sent'
        changed = mapped

    if fields:
        commande.save(update_fields=fields)
    if changed:
        notify_client_status(commande, changed)
    return changed
