"""Importe maintenant le catalogue partenaire (ex : mes_plats <- JEMLI "restaurant").

La vue `category/<type>/` le fait déjà toutes les 10 minutes ; cette commande
sert au premier import (téléversement des images) ou à forcer une mise à jour :

    python manage.py sync_partner_catalog            # tous les types concernés
    python manage.py sync_partner_catalog mes_plats
"""
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

from api.models import DeliveryType
from api.services.catalog import SYNC_TTL_SECONDS, _cache_key, sync_partner_catalog


class Command(BaseCommand):
    help = "Importe le catalogue des partenaires dans les catégories."

    def add_arguments(self, parser):
        parser.add_argument('types', nargs='*', help="Codes DeliveryType (défaut : tous).")

    def handle(self, *args, **options):
        delivery_types = (
            DeliveryType.objects
            .filter(is_active=True, provider__isnull=False)
            .exclude(catalog_category='')
            .select_related('provider')
        )
        if options['types']:
            delivery_types = delivery_types.filter(code__in=options['types'])

        if not delivery_types:
            raise CommandError('Aucun type avec catalogue partenaire.')

        for delivery_type in delivery_types:
            count = sync_partner_catalog(delivery_type)
            cache.set(_cache_key(delivery_type.code), True, SYNC_TTL_SECONDS)
            self.stdout.write(f'{delivery_type.code} : {count} produit(s) actif(s).')
