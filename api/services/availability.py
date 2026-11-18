"""Disponibilité horaire des articles du catalogue partenaire.

JEMLI fournit pour chaque produit `hours` : la liste des heures (0-23) pendant
lesquelles il peut être commandé, ex. [12, 13, 14] = de 12:00 à 14:59. Une
liste vide signifie « toujours disponible ». Les heures sont lues dans le fuseau
de Nouakchott (UTC+0, sans heure d'été).

Le moment contrôlé est celui où la commande part chez le partenaire :
`delivery_datetime` pour une commande programmée, sinon maintenant.
L'app (lib/core/utils/availability.dart) applique la même règle pour ne
proposer que des créneaux valides ; ce module reste l'autorité.
"""
from zoneinfo import ZoneInfo

from django.utils import timezone

NOUAKCHOTT = ZoneInfo('Africa/Nouakchott')


def parse_hours(raw):
    """Normalise la valeur `hours` du partenaire en liste triée d'entiers 0-23."""
    if not isinstance(raw, list):
        return []
    hours = set()
    for value in raw:
        try:
            hour = int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= hour <= 23:
            hours.add(hour)
    return sorted(hours)


def is_available_at(category, moment=None):
    hours = category.available_hours or []
    if not hours:
        return True
    moment = moment or timezone.now()
    return moment.astimezone(NOUAKCHOTT).hour in hours


def unavailable_categories(categories, moment=None):
    """Articles qui ne peuvent pas être commandés au moment donné."""
    return [c for c in categories if not is_available_at(c, moment)]
