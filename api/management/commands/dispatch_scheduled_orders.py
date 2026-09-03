"""Envoie au partenaire les commandes planifiées dont l'heure de livraison
est atteinte (typiquement mes_plats).

À lancer périodiquement (systemd timer / cron, ~chaque minute) :

    python manage.py dispatch_scheduled_orders
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from api.models import Commande
from api.services.delivery import send_to_partner


class Command(BaseCommand):
    help = "Déclenche l'envoi des commandes planifiées arrivées à échéance."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Liste les commandes concernées sans rien envoyer.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        due = (
            Commande.objects
            .filter(dispatch_status='scheduled', delivery_datetime__lte=now)
            .select_related('delivery_provider', 'delivery_provider__origin_point',
                            'delivery_type', 'location_point', 'user')
            .order_by('delivery_datetime')
        )

        if not due:
            self.stdout.write('Aucune commande à envoyer.')
            return

        for commande in due:
            if options['dry_run']:
                self.stdout.write(f'[dry-run] {commande.code} (prévu {commande.delivery_datetime})')
                continue

            ok = send_to_partner(commande)
            status = self.style.SUCCESS('OK') if ok else self.style.ERROR('ÉCHEC')
            self.stdout.write(f'{commande.code} -> {status}')
