"""Modification des plats d'une commande par un admin (app admin → détail
commande → « Modifier les plats »).

Règles :
- Modifiable tant que la commande n'est ni prise en charge ni en préparation
  (EDITABLE_STATUSES). Une commande restaurant JEMLI (type avec catalogue,
  ex. mes_plats) ne l'est plus une fois envoyée à JEMLI : leur API ne permet
  pas de modifier une commande reçue.
- Les lignes existantes gardent leur prix ; une ligne ajoutée prend le prix
  catalogue (-5 % pour un traiteur, comme CategoryByTypeView). Tous les plats
  restent du type de la commande (panier mono-type).
- Livraison et frais de service inchangés ; la promotion de la commande est
  recalculée sur le nouveau prix ; le crédit utilisé est plafonné au total.
- `paid_amount` ne bouge pas : `Commande.amount_due` donne le complément à
  payer (ou le trop-perçu), que TwizePay sait rapprocher (payments.py).
"""
from django.db import transaction
from django.utils import timezone

from ..models import Category, ItemCommande
from .pricing import _discount

EDITABLE_STATUSES = {'waiting', 'paid', 'looking_for_driver', 'driver_assigned'}


class OrderEditError(Exception):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def is_editable(commande):
    if commande.status not in EDITABLE_STATUSES:
        return False
    delivery_type = commande.delivery_type
    if delivery_type is not None and delivery_type.catalog_category and commande.dispatch_status == 'sent':
        return False
    return True


def _catalog_price(category, user):
    price = category.price1
    if getattr(user, 'type', None) == 'traitor':
        price = round(price * 0.95, 2)
    return price


def _plan(commande, lines):
    """Valide les lignes demandées et calcule le résultat, sans rien écrire.

    `lines` : [{"id"?: <ItemCommande>, "category_id", "number", "remplissage"?,
    "chicken_number"?}]. Renvoie (lignes normalisées, montants).
    """
    if not is_editable(commande):
        raise OrderEditError('not_editable', "Cette commande ne peut plus être modifiée.")
    if not isinstance(lines, list) or not lines:
        raise OrderEditError('empty', 'La commande doit garder au moins un plat.')

    existing = {item.id: item for item in commande.items.select_related('category')}
    order_type = commande.order_type
    ids = {line.get('category_id') for line in lines if isinstance(line, dict)}
    categories = {c.id: c for c in Category.objects.filter(pk__in=[i for i in ids if i is not None])}

    planned = []
    for line in lines:
        if not isinstance(line, dict):
            raise OrderEditError('invalid', 'Ligne invalide.')
        try:
            number = int(line.get('number'))
        except (TypeError, ValueError):
            raise OrderEditError('invalid', 'Quantité invalide.')
        if number < 1:
            continue  # quantité 0 = ligne retirée
        item = existing.get(line.get('id'))
        if item is not None:
            category, price = item.category, item.selected_price
        else:
            category = categories.get(line.get('category_id'))
            if category is None or not category.is_active:
                raise OrderEditError('invalid_item', 'Plat introuvable ou indisponible.')
            price = _catalog_price(category, commande.user)
        if order_type and category.type != order_type:
            raise OrderEditError('wrong_type', 'Tous les plats doivent être du même type que la commande.')
        planned.append({
            'item': item,
            'category': category,
            'number': number,
            'selected_price': price,
            'remplissage': line.get('remplissage', item.remplissage if item else 'aucun') or 'aucun',
            'chicken_number': int(line.get('chicken_number', item.chicken_number if item else 0) or 0),
        })
    if not planned:
        raise OrderEditError('empty', 'La commande doit garder au moins un plat.')

    prix = round(sum(p['number'] * p['selected_price'] for p in planned), 2)
    livraison = commande.livraison or 0
    discount, delivery_discount = (0, 0)
    if commande.promotion is not None:
        discount, delivery_discount = _discount(commande.promotion, prix, livraison)
    subtotal = prix + livraison + (commande.service_fee or 0) - discount - delivery_discount
    credit_used = round(min(commande.credit_used or 0, max(subtotal, 0)), 2)
    totals = {
        'prix': prix,
        'discount_amount': discount,
        'delivery_discount': delivery_discount,
        'credit_used': credit_used,
    }
    return planned, totals


def preview_items_edit(commande, lines):
    """Montants après modification, pour l'affichage avant validation."""
    _, totals = _plan(commande, lines)
    before_total, before_due = commande.total_amount, commande.amount_due
    for field, value in totals.items():
        setattr(commande, field, value)
    result = {
        **totals,
        'previous_total': before_total,
        'total_amount': commande.total_amount,
        'previous_amount_due': before_due,
        'amount_due': commande.amount_due,
        'paid_amount': commande.paid_amount,
    }
    commande.refresh_from_db()
    return result


@transaction.atomic
def apply_items_edit(commande, lines):
    """Remplace les plats de la commande. Renvoie le résultat de preview."""
    commande = type(commande).objects.select_for_update().get(pk=commande.pk)
    planned, totals = _plan(commande, lines)
    before_total, before_due = commande.total_amount, commande.amount_due

    kept = set()
    for p in planned:
        item = p['item'] or ItemCommande(commande=commande, category=p['category'], selected_price=p['selected_price'])
        item.number = p['number']
        item.remplissage = p['remplissage']
        item.chicken_number = p['chicken_number']
        item.with_chicken = p['chicken_number'] > 0
        item.save()
        kept.add(item.pk)
    commande.items.exclude(pk__in=kept).delete()

    for field, value in totals.items():
        setattr(commande, field, value)
    commande.items_edited_at = timezone.now()
    commande.save(update_fields=[*totals, 'items_edited_at'])
    return commande, {
        **totals,
        'previous_total': before_total,
        'total_amount': commande.total_amount,
        'previous_amount_due': before_due,
        'amount_due': commande.amount_due,
        'paid_amount': commande.paid_amount,
    }
