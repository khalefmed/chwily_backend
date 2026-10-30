"""Client HTTP pour l'API du partenaire de livraison JEMLI.

Auth : en-têtes X-Api-Key / X-Api-Secret.

⚠️ Le segment de route (`10/2026`, auparavant `28/08/2026`) est fourni par
JEMLI et fait partie de `DeliveryProvider.base_url` ; ce client ne le calcule
pas. JEMLI l'a changé sans prévenir (constaté le 2026-10-26 : l'ancien segment
renvoie 404 sur toutes les routes) — un 404 sur toutes les routes JEMLI
signifie probablement un nouveau changement de segment.

Confirmé (compute-pricing, requête réelle) :
    -> {"price": 0.0, "delivery_fee": 100.0, "distance_km": 4.13,
        "origin_title": "...", "destination_title": "...", "is_prepaid": true}
    "delivery_fee" est le tarif de livraison à utiliser (pas "price").

Référence complète (routes, formats, niveau de confiance) : docs/jemli-api.md.
Les corps de `deliveries/` et `orders/` suivent la description de JEMLI, mais
leurs réponses n'ont jamais été observées (appels réels = vrai livreur / vrai
restaurant). Marqué TODO(jemli-doc).
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
        # provider.base_url contient déjà le segment de route JEMLI (ex. .../10/2026/).
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

    @staticmethod
    def _reference(commande):
        # Seul champ libre transmis au livreur : notre code + le téléphone du
        # destinataire (deliveries/ n'a pas de champ téléphone).
        return f'Chwily {commande.code} - {commande.phone}'

    def create_delivery(self, commande):
        """Course seule (sbou7 / poisson / l7am) — corps décrit par JEMLI
        (OPTIONS deliveries/), réponse jamais observée : voir docs/jemli-api.md."""
        origin = commande.delivery_provider.origin_point
        destination = commande.destination
        if origin is None or destination is None:
            raise DeliveryPartnerError('Point de départ ou destination manquant.')

        payload = {
            'origin': self._point(origin),
            'destination': self._point(destination),
            'custom_description': self._reference(commande),
            'origin_title': origin.name,
        }
        if commande.location_point is not None:
            payload['destination_title'] = commande.location_point.name

        url = f'{self._base()}/deliveries/'
        return self._request('POST', url, json=payload)

    def create_order(self, commande, category):
        """Commande restaurant (plats + livraison depuis le vendeur), pour les
        types alimentés par le catalogue (mes_plats -> restaurant).
        Corps décrit par JEMLI (OPTIONS orders/), réponse jamais observée."""
        destination = commande.destination
        if destination is None:
            raise DeliveryPartnerError('Destination manquante.')

        items = []
        for item in commande.items.select_related('category'):
            if not item.category.external_id:
                raise DeliveryPartnerError(
                    f'Article « {item.category.name_fr} » absent du catalogue partenaire.'
                )
            items.append({'product_id': int(item.category.external_id), 'quantity': item.number})
        if not items:
            raise DeliveryPartnerError('Commande sans article.')

        user = commande.user
        reference = self._reference(commande)
        payload = {
            'phone': commande.phone,
            'full_name': user.get_full_name() or commande.title or '',
            'destination': self._point(destination),
            'items': items,
            # La docstring JEMLI dit customer_description, leur exemple
            # custom_description : on envoie les deux tant que ce n'est pas tranché.
            'customer_description': reference,
            'custom_description': reference,
        }
        url = f'{self._base()}/orders/'
        return self._request('POST', url, params={'category': category}, json=payload)

    def get_delivery(self, ref):
        url = f'{self._base()}/deliveries/{ref}/'
        return self._request('GET', url)

    def list_products(self, category):
        """Catalogue du vendeur lié aux clés API (le vendeur n'est pas paramétrable).

        Confirmé (requête réelle, 2026-10-26) ; seule `category=restaurant` est acceptée :
            -> {"category": "restaurant", "vendor_id": 472, "products": [
                  {"id", "name", "description", "price", "discount_price",
                   "image" (URL absolue), "menus": [{"id", "name"}]}]}
        Pas de pagination.
        """
        url = f'{self._base()}/products/'
        return self._request('GET', url, params={'category': category})


# --- Extraction de valeurs depuis les réponses JEMLI. ------------------
# `delivery_fee` est confirmé (voir docstring). Le reste garde un
# repli défensif tant que `deliveries/` n'est pas vérifié.

_PRICE_KEYS = ('delivery_fee', 'price', 'amount', 'total', 'fee', 'cost', 'pricing', 'total_price')
_REF_KEYS = ('id', 'delivery_id', 'reference', 'ref', 'tracking_id', 'uuid')
_WRAPPERS = ('data', 'result', 'results', 'delivery', 'order', 'pricing', 'payload')


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
