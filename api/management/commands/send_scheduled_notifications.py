"""Envoie les notifications programmées arrivées à échéance (admin de l'app :
Gestion → Notifications programmées).

Lancée chaque minute par le même timer systemd que dispatch_scheduled_orders
(voir deploy/chwily-dispatch.service) :

    python manage.py send_scheduled_notifications
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from api.models import ScheduledNotification
from api.services.notifications import send_broadcast

# Au-delà, l'envoi n'a plus de sens (timer arrêté longtemps) : on abandonne
# plutôt que de pousser un message périmé à tous les clients.
MAX_DELAY = timedelta(hours=1)


class Command(BaseCommand):
    help = 'Envoie les notifications programmées arrivées à échéance.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Liste sans envoyer.')

    def handle(self, *args, **options):
        now = timezone.now()
        with transaction.atomic():
            due = list(
                ScheduledNotification.objects.select_for_update(skip_locked=True)
                .filter(status='pending', send_at__lte=now).order_by('send_at')
            )
            if options['dry_run']:
                for notif in due:
                    self.stdout.write(f'[dry-run] {notif}')
                return
            for notif in due:
                if now - notif.send_at > MAX_DELAY:
                    notif.status, notif.error = 'failed', 'Expirée : non envoyée à temps.'
                else:
                    try:
                        send_broadcast(notif.title, notif.body)
                        notif.status, notif.sent_at = 'sent', timezone.now()
                    except Exception as exc:
                        notif.status, notif.error = 'failed', str(exc)[:300]
                notif.save(update_fields=['status', 'sent_at', 'error'])
                self.stdout.write(f'{notif.status} : {notif}')
