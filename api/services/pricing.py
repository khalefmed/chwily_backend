"""Montant d'une commande : frais de service, promotions, crédit fidélité.

Le backend fait autorité : l'app affiche l'aperçu de `POST commandes/pricing/`
et `AddCommandeView` refait le même calcul à la création (le total sert au
rapprochement TwizePay, voir payments.py).

    total = prix + livraison + frais de service
            - remise promo (articles ou livraison) - crédit utilisé

Règles :
- Une seule promotion par commande : la plus avantageuse parmi les promotions
  automatiques actives (sans code) et le code saisi. À remise égale, le code
  l'emporte.
- La remise « montant » / « pourcentage » porte sur le prix des articles
  uniquement ; « livraison gratuite » annule la livraison.
- Le crédit fidélité s'ajoute à la promotion et couvre tout le reste à payer.
- Une commande « engage » sa promotion et son crédit tant qu'elle n'est pas
  rejetée ni abandonnée (en attente de paiement depuis plus de MATCH_WINDOW) :
  une commande jamais payée rend donc le crédit et l'utilisation du code.
"""
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Optional

from django.db.models import Sum
from django.utils import timezone

from ..models import AppConfiguration, Commande, CreditTransaction, Promotion

# Même fenêtre que le rapprochement TwizePay : au-delà, une commande en
# attente n'est plus payable, elle ne bloque plus ni crédit ni code promo.
ABANDON_AFTER = timedelta(hours=24)


@dataclass
class Pricing:
    prix: float
    livraison: float
    service_fee: float = 0
    discount_amount: float = 0
    delivery_discount: float = 0
    credit_used: float = 0
    credit_balance: float = 0
    promotion: Optional[Promotion] = None
    promo_code: str = ''
    promo_error: str = ''
    loyalty: dict = field(default_factory=dict)

    @property
    def total(self):
        total = (self.prix + self.livraison + self.service_fee
                 - self.discount_amount - self.delivery_discount - self.credit_used)
        return round(max(total, 0), 2)

    def as_dict(self):
        data = asdict(self)
        promotion = data.pop('promotion')
        data['promotion'] = None if self.promotion is None else {
            'id': self.promotion.id,
            'name': self.promotion.name,
            'code': self.promotion.code,
            'discount_type': self.promotion.discount_type,
            'value': self.promotion.value,
        }
        data['total'] = self.total
        return data


def engaged_commandes(now=None):
    """Commandes qui consomment crédit et code promo (ni rejetées ni abandonnées)."""
    now = now or timezone.now()
    return Commande.objects.exclude(status='rejected').exclude(
        status='waiting', date__lt=now - ABANDON_AFTER,
    )


def credit_balance(user, now=None):
    earned = CreditTransaction.objects.filter(user=user).aggregate(s=Sum('amount'))['s'] or 0
    spent = engaged_commandes(now).filter(user=user).aggregate(s=Sum('credit_used'))['s'] or 0
    return round(max(earned - spent, 0), 2)


def _discount(promotion, prix, livraison):
    """(remise articles, remise livraison) que donnerait la promotion."""
    if promotion.discount_type == 'free_delivery':
        return 0, livraison
    if promotion.discount_type == 'percent':
        amount = prix * (promotion.value or 0) / 100
        if promotion.max_discount is not None:
            amount = min(amount, promotion.max_discount)
    else:
        amount = promotion.value or 0
    return round(min(max(amount, 0), prix), 2), 0


def _active_promotions(now):
    return Promotion.objects.filter(is_active=True, starts_at__lte=now, ends_at__gt=now)


def _usage_error(promotion, user, prix, now):
    """Code d'erreur si la promotion ne peut pas s'appliquer, sinon ''."""
    if prix < (promotion.min_order_amount or 0):
        return 'min_order'
    if promotion.max_uses is None and promotion.max_uses_per_user is None:
        return ''
    uses = engaged_commandes(now).filter(promotion=promotion)
    if promotion.max_uses is not None and uses.count() >= promotion.max_uses:
        return 'exhausted'
    if promotion.max_uses_per_user is not None and uses.filter(user=user).count() >= promotion.max_uses_per_user:
        return 'already_used'
    return ''


def _find_code(code, now):
    """(promotion, erreur) pour le code saisi."""
    promotion = Promotion.objects.filter(code=code, is_active=True).first()
    if promotion is None:
        return None, 'invalid'
    if now < promotion.starts_at:
        return None, 'not_started'
    if now >= promotion.ends_at:
        return None, 'expired'
    return promotion, ''


def loyalty_progress(user, config=None):
    """Où en est le client vers sa prochaine récompense (vide si désactivé)."""
    config = config or AppConfiguration.current()
    if not config.loyalty_enabled or config.loyalty_orders_count < 1 or config.loyalty_reward_amount <= 0:
        return {}
    delivered = Commande.objects.filter(user=user, status='delivered').count()
    step = config.loyalty_orders_count
    return {
        'orders_count': step,
        'reward_amount': config.loyalty_reward_amount,
        'delivered_orders': delivered,
        'orders_remaining': step - delivered % step,
    }


def compute_pricing(user, prix, livraison, promo_code='', now=None):
    """Calcule le montant d'une commande (pas encore créée) pour `user`."""
    now = now or timezone.now()
    config = AppConfiguration.current()
    prix = round(max(float(prix or 0), 0), 2)
    livraison = round(max(float(livraison or 0), 0), 2)
    code = (promo_code or '').strip().upper()
    pricing = Pricing(prix=prix, livraison=livraison, service_fee=round(config.service_fee or 0, 2), promo_code=code)

    # Candidats : promotions automatiques actives + le code saisi.
    candidates = [p for p in _active_promotions(now).filter(code='') if not _usage_error(p, user, prix, now)]
    code_promotion = None
    if code:
        code_promotion, pricing.promo_error = _find_code(code, now)
        if code_promotion is not None:
            pricing.promo_error = _usage_error(code_promotion, user, prix, now)
            if pricing.promo_error:
                code_promotion = None

    best, best_total = None, 0
    for promotion in candidates + ([code_promotion] if code_promotion else []):
        discount, delivery_discount = _discount(promotion, prix, livraison)
        # `>=` : à remise égale, le code (dernier candidat) l'emporte.
        if discount + delivery_discount > 0 and discount + delivery_discount >= best_total:
            best, best_total = promotion, discount + delivery_discount
    if best is not None:
        pricing.promotion = best
        pricing.discount_amount, pricing.delivery_discount = _discount(best, prix, livraison)
    if code_promotion is not None and best is not code_promotion:
        pricing.promo_error = 'better_promotion_applied'

    balance = credit_balance(user, now)
    pricing.credit_balance = balance
    pricing.credit_used = round(min(balance, pricing.total), 2)
    pricing.loyalty = loyalty_progress(user, config)
    return pricing


def apply_pricing(commande, pricing):
    """Recopie le calcul sur la commande (sans sauvegarder)."""
    commande.service_fee = pricing.service_fee
    commande.promotion = pricing.promotion
    commande.promo_code = pricing.promo_code if pricing.promotion and pricing.promotion.code else ''
    commande.discount_amount = pricing.discount_amount
    commande.delivery_discount = pricing.delivery_discount
    commande.credit_used = pricing.credit_used


def grant_loyalty_rewards(commande):
    """Appelée quand une commande passe à `delivered` : crédite le client de
    toutes les récompenses dues (delivered // X) non encore versées.
    Idempotent : rejouer le même statut ne crédite rien de plus."""
    config = AppConfiguration.current()
    if not config.loyalty_enabled or config.loyalty_orders_count < 1 or config.loyalty_reward_amount <= 0:
        return 0
    user = commande.user
    delivered = Commande.objects.filter(user=user, status='delivered').count()
    due = delivered // config.loyalty_orders_count
    given = CreditTransaction.objects.filter(user=user, kind='loyalty_reward').count()
    for _ in range(max(due - given, 0)):
        CreditTransaction.objects.create(
            user=user, amount=config.loyalty_reward_amount, kind='loyalty_reward', commande=commande,
            note=f'{config.loyalty_orders_count} commandes livrées',
        )
    return max(due - given, 0)
