"""Paiements wallet détectés par TwizePay : vérification du webhook,
enregistrement des transactions et rapprochement avec les commandes.

Règle de rapprochement : une transaction entrante (CR) paie la plus ancienne
commande `waiting` dont `payment_phone` est le numéro payeur et dont le
montant total (prix + livraison) est égal au montant reçu. Le rapprochement
se fait dans les deux sens : à la réception du paiement, et à la création de
la commande (le client peut payer avant de valider sa commande).
"""
import hashlib
import hmac
import logging
import re
import threading
import time
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import close_old_connections, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..models import Commande, WalletTransaction
from .delivery import dispatch_commande, notify_client_status
from .notifications import send_notifications_to_admins

logger = logging.getLogger(__name__)

SIGNATURE_TOLERANCE_SECONDS = 300
# Une commande et un paiement plus anciens que ça ne sont plus rapprochés.
MATCH_WINDOW = timedelta(hours=24)
AMOUNT_TOLERANCE = Decimal('0.01')


def normalize_phone(value):
    """Numéro mauritanien sur 8 chiffres : '+222 36 89 99 00' -> '36899900'."""
    digits = re.sub(r'\D', '', str(value or ''))
    return digits[-8:] if len(digits) >= 8 else digits


def verify_signature(secret, signature_header, timestamp_header, raw_body):
    """Vérification TwizePay : HMAC-SHA256 de `<t>.<corps brut>`, en hexa."""
    if not secret or not signature_header:
        return False
    parts = {}
    for part in signature_header.split(','):
        key, _, value = part.partition('=')
        parts[key.strip()] = value.strip()
    try:
        timestamp = int(parts['t'])
    except (KeyError, ValueError):
        return False
    if str(timestamp) != str(timestamp_header):
        return False
    if abs(int(time.time()) - timestamp) > SIGNATURE_TOLERANCE_SECONDS:
        return False
    signed = str(timestamp).encode() + b'.' + raw_body
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts.get('v1', ''))


def _decimal(value):
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'))
    except InvalidOperation:
        return None


def record_transaction(payload, event_id=''):
    """Crée ou complète la transaction `payload['id']` (idempotent : un envoi
    rejoué ou un `transaction.updated` ne crée jamais un second paiement).
    Retourne la transaction, ou None si le corps est inexploitable."""
    external_id = str(payload.get('id') or '').strip()
    amount = _decimal(payload.get('amount'))
    direction = str(payload.get('direction') or '').upper()
    if not external_id or amount is None or direction not in ('CR', 'DR'):
        return None

    fields = {
        'bank_reference': str(payload.get('transactionId') or ''),
        'wallet': str(payload.get('wallet') or ''),
        'direction': direction,
        'amount': amount,
        'balance_after': _decimal(payload.get('balanceAfter')),
        'occurred_at': parse_datetime(payload['occurredAt']) if payload.get('occurredAt') else None,
        'last_event_id': event_id,
        'raw': payload,
    }
    # `transaction.updated` complète un numéro ou un nom vide : on ne remplace
    # jamais une valeur connue par une valeur nulle.
    if payload.get('counterpartyNumber'):
        fields['counterparty_number'] = str(payload['counterpartyNumber'])
        fields['payer_phone'] = normalize_phone(payload['counterpartyNumber'])
    if payload.get('counterpartyName'):
        fields['counterparty_name'] = str(payload['counterpartyName'])

    tx, created = WalletTransaction.objects.update_or_create(external_id=external_id, defaults=fields)
    if created and direction == 'DR':
        tx.match_status = 'ignored'
        tx.save(update_fields=['match_status'])
    return tx


def _amount_matches(commande, amount):
    return abs(Decimal(str(commande.total_amount)) - amount) <= AMOUNT_TOLERANCE


def match_transaction(tx):
    """Paiement reçu -> commande en attente. Retourne la commande payée ou None."""
    if tx.match_status != 'pending' or tx.direction != 'CR' or not tx.payer_phone:
        return None

    with transaction.atomic():
        tx = WalletTransaction.objects.select_for_update().get(pk=tx.pk)
        if tx.match_status != 'pending':
            return None
        candidates = (
            Commande.objects.select_for_update()
            .filter(status='waiting', payment_phone=tx.payer_phone, date__gte=timezone.now() - MATCH_WINDOW)
            .order_by('date')
        )
        commande = next((c for c in candidates if _amount_matches(c, tx.amount)), None)
        if commande is None:
            if candidates:
                waiting_pk = candidates[0].pk
                transaction.on_commit(lambda: _in_background(_alert_amount_mismatch, tx.pk, waiting_pk))
            return None
        _link(tx, commande)
    return commande


def match_commande(commande):
    """Commande créée -> paiement déjà reçu. Retourne la transaction ou None."""
    if commande.status != 'waiting' or not commande.payment_phone:
        return None

    with transaction.atomic():
        commande = Commande.objects.select_for_update().get(pk=commande.pk)
        if commande.status != 'waiting':
            return None
        candidates = (
            WalletTransaction.objects.select_for_update()
            .filter(match_status='pending', direction='CR', payer_phone=commande.payment_phone,
                    received_at__gte=timezone.now() - MATCH_WINDOW)
            .order_by('received_at')
        )
        tx = next((t for t in candidates if _amount_matches(commande, t.amount)), None)
        if tx is None:
            return None
        _link(tx, commande)
    return tx


def _link(tx, commande):
    """Dans la transaction DB : marque le paiement et la commande, puis lance
    l'envoi au livreur et les notifications une fois la transaction validée."""
    tx.commande = commande
    tx.match_status = 'matched'
    tx.matched_at = timezone.now()
    tx.save(update_fields=['commande', 'match_status', 'matched_at'])
    commande.status = 'paid'
    commande.save(update_fields=['status'])
    logger.info('Commande %s payée automatiquement par la transaction TwizePay %s', commande.code, tx.external_id)
    transaction.on_commit(lambda: _in_background(_after_paid, commande.pk, tx.pk))


def _in_background(func, *args):
    """TwizePay coupe à 10 s et JEMLI peut prendre 20 s : l'envoi au partenaire
    et les push partent après la réponse au webhook."""
    def run():
        try:
            func(*args)
        except Exception:
            logger.exception('Traitement post-paiement échoué')
        finally:
            close_old_connections()
    threading.Thread(target=run, daemon=True).start()


def _after_paid(commande_pk, tx_pk):
    commande = Commande.objects.select_related('user').get(pk=commande_pk)
    tx = WalletTransaction.objects.get(pk=tx_pk)
    try:
        dispatch_commande(commande)
    except Exception:
        logger.exception('dispatch_commande a échoué pour %s', commande.code)
    # dispatch_commande notifie déjà le client s'il a fait évoluer le statut.
    if commande.status == 'paid':
        notify_client_status(commande, 'paid')
    send_notifications_to_admins(
        'Paiement reçu',
        f'Commande {commande.code} payée automatiquement : {tx.amount} MRU via {tx.wallet or "wallet"} '
        f'depuis le {tx.counterparty_number}.',
    )


def _alert_amount_mismatch(tx_pk, commande_pk):
    """Le numéro payeur a une commande en attente, mais pas de ce montant."""
    tx = WalletTransaction.objects.get(pk=tx_pk)
    commande = Commande.objects.get(pk=commande_pk)
    send_notifications_to_admins(
        'Paiement à vérifier',
        f'{tx.amount} MRU reçus du {tx.counterparty_number}, mais la commande {commande.code} '
        f'attend {commande.total_amount:g} MRU.',
    )
