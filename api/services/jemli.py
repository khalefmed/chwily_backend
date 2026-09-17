"""Client HTTP pour l'API du partenaire de livraison JEMLI.

Auth : en-têtes X-Api-Key / X-Api-Secret.

⚠️ Le segment `28/08/2026` dans l'URL type ressemble à une date mais n'EN
EST PAS UNE : testé empiriquement le 2026-09-17 contre l'API réelle, toutes
les autres dates (y compris le jour même) renvoient 404 — seul ce segment
fixe fonctionne. C'est un identifiant de route propre à notre compte
partenaire, fourni par JEMLI. Il fait donc partie de `DeliveryProvider.base_url`
(ex. `https://api-jemli.oneposts.io/api/third-party/28/08/2026/`) et n'est
PAS recalculé par ce client.

Confirmé (compute-pricing, requête réelle) :
    -> {"price": 0.0, "delivery_fee": 100.0, "distance_km": 4.13,
        "origin_title": "...", "destination_title": "...", "is_prepaid": true}
    "delivery_fee" est le tarif de livraison à utiliser (pas "price").

⚠️ Le corps/la réponse de `deliveries/` (création) restent non vérifiés —
volontairement pas testés en conditions réelles pour ne pas déclencher une
vraie livraison. Marqué TODO(jemli-doc).
"""
import logging

import requests

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
        # provider.base_url contient déjà le segment de route JEMLI (ex. .../28/08/2026/).
        return self.provider.base_url.rstrip('/')

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
    def compute_pricing(self, origin, destination):
        url = f'{self._base()}/compute-pricing/'
        return self._request('POST', url, json={
            'origin': self._point(origin),
            'destination': self._point(destination),
        })

    def create_delivery(self, commande):
        origin = commande.delivery_provider.origin_point
        destination = commande.location_point
        if origin is None or destination is None:
            raise DeliveryPartnerError('Point de départ ou destination manquant.')

        # TODO(jemli-doc) : corps non vérifié en conditions réelles (voir
        # docstring du module) — compléter/corriger une fois testé.
        payload = {
            'origin': self._point(origin),
            'destination': self._point(destination),
            'reference': commande.code,
            'recipient_phone': commande.phone,
            'recipient_name': commande.title or '',
        }
        if commande.delivery_datetime:
            payload['scheduled_at'] = commande.delivery_datetime.isoformat()

        url = f'{self._base()}/deliveries/'
        return self._request('POST', url, json=payload)

    def get_delivery(self, ref):
        url = f'{self._base()}/deliveries/{ref}/'
        return self._request('GET', url)


# --- Extraction de valeurs depuis les réponses JEMLI. ------------------
# `delivery_fee` est confirmé (voir docstring). Le reste garde un
# repli défensif tant que `deliveries/` n'est pas vérifié.

_PRICE_KEYS = ('delivery_fee', 'price', 'amount', 'total', 'fee', 'cost', 'pricing', 'total_price')
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
