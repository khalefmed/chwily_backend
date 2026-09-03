"""Client HTTP pour l'API du partenaire de livraison JEMLI.

Base : https://api-jemli.oneposts.io/api/third-party/
Auth : en-têtes X-Api-Key / X-Api-Secret
Les endpoints portent la date de livraison dans l'URL : /DD/MM/YYYY/...

⚠️  Le format exact des corps / réponses (au-delà de ce que montrent les
exemples curl fournis) reste à confirmer avec la doc JEMLI. Les endroits
concernés sont marqués « TODO(jemli-doc) ».
"""
import logging

import requests
from django.utils import timezone

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20


class DeliveryPartnerError(Exception):
    """Erreur en communiquant avec un partenaire de livraison."""


class JemliClient:
    def __init__(self, provider):
        self.provider = provider

    # -- interne -------------------------------------------------------
    def _headers(self):
        return {
            'Content-Type': 'application/json',
            'X-Api-Key': self.provider.api_key,
            'X-Api-Secret': self.provider.api_secret,
        }

    def _base(self):
        return self.provider.base_url.rstrip('/')

    @staticmethod
    def _date_segment(when=None):
        when = when or timezone.localtime()
        if timezone.is_aware(when):
            when = timezone.localtime(when)
        return when.strftime('%d/%m/%Y')

    @staticmethod
    def _point(location_point):
        return {'lat': location_point.lat, 'lng': location_point.lng}

    def _request(self, method, url, **kwargs):
        try:
            resp = requests.request(
                method, url, headers=self._headers(), timeout=DEFAULT_TIMEOUT, **kwargs
            )
        except requests.RequestException as exc:
            logger.exception('JEMLI %s %s a échoué', method, url)
            raise DeliveryPartnerError(str(exc)) from exc

        if resp.status_code >= 400:
            logger.error('JEMLI %s %s -> %s : %s', method, url, resp.status_code, resp.text[:500])
            raise DeliveryPartnerError(f'{resp.status_code}: {resp.text[:500]}')

        try:
            return resp.json()
        except ValueError:
            return {}

    # -- API ----------------------------------------------------------
    def compute_pricing(self, origin, destination, when=None):
        url = f'{self._base()}/{self._date_segment(when)}/compute-pricing/'
        return self._request('POST', url, json={
            'origin': self._point(origin),
            'destination': self._point(destination),
        })

    def create_delivery(self, commande, when=None):
        origin = commande.delivery_provider.origin_point
        destination = commande.location_point
        if origin is None or destination is None:
            raise DeliveryPartnerError('Point de départ ou destination manquant.')

        # TODO(jemli-doc) : compléter le corps (nom / téléphone du
        # destinataire, référence, créneau, contenu…) une fois la doc reçue.
        payload = {
            'origin': self._point(origin),
            'destination': self._point(destination),
            'reference': commande.code,
            'recipient_phone': commande.phone,
            'recipient_name': commande.title or '',
        }
        if commande.delivery_datetime:
            payload['scheduled_at'] = commande.delivery_datetime.isoformat()

        segment_date = when or commande.delivery_datetime
        url = f'{self._base()}/{self._date_segment(segment_date)}/deliveries/'
        return self._request('POST', url, json=payload)

    def get_delivery(self, ref, when=None):
        url = f'{self._base()}/{self._date_segment(when)}/deliveries/{ref}/'
        return self._request('GET', url)


# --- Extraction défensive de valeurs depuis des réponses au schéma
#     encore non confirmé. TODO(jemli-doc) : figer les clés. ----------

_PRICE_KEYS = ('price', 'amount', 'total', 'fee', 'cost', 'delivery_fee', 'pricing', 'total_price')
_REF_KEYS = ('id', 'delivery_id', 'reference', 'ref', 'tracking_id', 'uuid')
_WRAPPERS = ('data', 'result', 'results', 'delivery', 'pricing', 'payload')


def _dig(payload, keys):
    if isinstance(payload, (int, float)) and keys is _PRICE_KEYS:
        return float(payload)
    if not isinstance(payload, dict):
        return None
    for key in keys:
        val = payload.get(key)
        if val not in (None, '', {}, []):
            if keys is _PRICE_KEYS:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
            return str(val)
    for wrapper in _WRAPPERS:
        if isinstance(payload.get(wrapper), dict):
            found = _dig(payload[wrapper], keys)
            if found is not None:
                return found
    return None


def extract_price(payload):
    price = _dig(payload, _PRICE_KEYS)
    if price is None:
        raise DeliveryPartnerError(f'Prix introuvable dans la réponse JEMLI : {payload!r}')
    return price


def extract_delivery_ref(payload):
    ref = _dig(payload, _REF_KEYS)
    if not ref:
        raise DeliveryPartnerError(f'ID de livraison introuvable dans la réponse JEMLI : {payload!r}')
    return ref
