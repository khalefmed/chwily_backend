"""Import du catalogue partenaire dans `Category`.

Un `DeliveryType` avec `catalog_category` (ex : mes_plats -> "restaurant")
voit ses articles alimentés par le catalogue du partenaire au lieu de l'admin.
Les produits sont recopiés en lignes `Category` (type = code du DeliveryType)
pour que panier, `ItemCommande` et commande restent inchangés côté app et API.

- Clé de rapprochement : `Category.external_id` = id produit partenaire.
- Images : le compte Cloudinary refuse le type "fetch", l'image partenaire est
  donc téléversée (public_id `jemli/products/<id>`), uniquement si elle change.
- Produit absent du catalogue -> `is_active=False` (jamais supprimé :
  ItemCommande.category est en CASCADE). Les articles saisis à la main pour ce
  type sont donc masqués eux aussi.
"""
import logging

import cloudinary.uploader
from cloudinary import CloudinaryResource
from django.core.cache import cache

from ..models import Category, DeliveryType
from .delivery import client_for
from .jemli import DeliveryPartnerError

logger = logging.getLogger(__name__)

SYNC_TTL_SECONDS = 600
RETRY_TTL_SECONDS = 60


def _cache_key(type_code):
    return f'partner_catalog_synced:{type_code}'


def _upload_image(provider_code, product_id, url):
    result = cloudinary.uploader.upload(
        url,
        public_id=f'{provider_code}/products/{product_id}',
        overwrite=True,
        resource_type='image',
    )
    return CloudinaryResource(
        public_id=result['public_id'],
        format=result.get('format'),
        version=result.get('version'),
        type='upload',
        resource_type='image',
    )


def sync_partner_catalog(delivery_type):
    """Importe le catalogue du partenaire. Renvoie le nombre de produits actifs.

    Lève DeliveryPartnerError si le partenaire ne répond pas correctement.
    """
    provider = delivery_type.provider
    payload = client_for(provider).list_products(delivery_type.catalog_category)
    products = payload.get('products')
    if not isinstance(products, list):
        raise DeliveryPartnerError(f'Réponse catalogue inattendue : {str(payload)[:200]}')

    type_code = delivery_type.code
    existing = {
        c.external_id: c
        for c in Category.objects.filter(type=type_code, external_id__isnull=False)
    }
    active_ids = []

    for position, product in enumerate(products):
        external_id = str(product['id'])
        name = product.get('name') or ''
        price = product.get('discount_price') or product.get('price') or 0
        image_url = product.get('image') or ''

        category = existing.get(external_id) or Category(
            type=type_code, type_class=type_code, external_id=external_id,
        )

        if image_url and image_url != category.external_image_url:
            try:
                category.image = _upload_image(provider.code, external_id, image_url)
                category.external_image_url = image_url
            except Exception:
                logger.exception('Image catalogue %s non téléversée : %s', external_id, image_url)
        if category.pk is None and not category.image:
            # Category.image est obligatoire (et lu tel quel par l'app) :
            # le produit sera retenté à la prochaine synchro.
            continue

        # Le partenaire ne fournit qu'un nom (en arabe).
        category.name_fr = name
        category.name_ar = name
        category.price1 = category.price2 = category.price3 = float(price)
        category.livraison = 0
        category.is_big_steak = False
        category.order = position
        category.is_active = True
        category.save()
        active_ids.append(category.pk)

    (Category.objects
     .filter(type=type_code, is_active=True)
     .exclude(pk__in=active_ids)
     .update(is_active=False))
    return len(active_ids)


def ensure_catalog_fresh(type_code):
    """Resynchronise le catalogue du type s'il en a un et que la dernière
    synchro date de plus de SYNC_TTL_SECONDS. N'échoue jamais : en cas d'erreur
    partenaire, les derniers produits importés restent servis."""
    key = _cache_key(type_code)
    if cache.get(key):
        return

    delivery_type = (
        DeliveryType.objects
        .filter(code=type_code, is_active=True, provider__isnull=False, provider__is_active=True)
        .exclude(catalog_category='')
        .select_related('provider')
        .first()
    )
    if delivery_type is None:
        cache.set(key, True, SYNC_TTL_SECONDS)
        return

    try:
        sync_partner_catalog(delivery_type)
    except Exception:
        logger.exception('Synchro du catalogue %s échouée', type_code)
        cache.set(key, True, RETRY_TTL_SECONDS)
        return
    cache.set(key, True, SYNC_TTL_SECONDS)
