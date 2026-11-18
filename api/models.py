from django.db import models
from phonenumber_field.modelfields import PhoneNumberField
from django.contrib.auth.models import AbstractUser, BaseUserManager, PermissionsMixin
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.hashers import make_password
import uuid
from cloudinary.models import CloudinaryField




class CustomUserManager(BaseUserManager):
    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('username', phone)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(phone, password, **extra_fields)

    def create_user(self, phone, password=None, **extra_fields):
        extra_fields.setdefault('username', phone)

        if not phone:
            raise ValueError('The mobile field must be set')

        user = self.model(phone=phone, **extra_fields)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user


class User(AbstractUser):
    phone = models.IntegerField(unique=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    USER_TYPE_CHOICES = [
        ('simple', 'Simple'),
        ('traitor', 'Traitor'),
        ('admin', 'Admin'),
        ('super_admin', 'Super Admin'),
    ]
    type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='simple')
    default_lang = models.CharField(max_length=5, default='fr')
    fcm_token = models.CharField(max_length=250, default='')

    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = ['email', 'first_name', 'last_name']

    objects = CustomUserManager()

    def __str__(self):
        return f'{self.phone}'

    def save(self, *args, **kwargs):

        if self.password:
            self.password = self.password

        super().save(*args, **kwargs)



class Category(models.Model):
    image = CloudinaryField('image')
    name_fr = models.CharField(max_length=100)
    name_ar = models.CharField(max_length=100, default='')
    price1 = models.FloatField()
    price2 = models.FloatField()
    price3 = models.FloatField()
    livraison = models.FloatField()
    type = models.CharField(max_length=50)
    is_big_steak = models.BooleanField(default=False)
    type_class = models.CharField(max_length=50)
    order = models.IntegerField(default=0)
    # Produits importés du catalogue partenaire (voir api/services/catalog.py) :
    # `external_id` = id produit JEMLI, `external_image_url` = image source
    # (déjà copiée dans `image` sur Cloudinary).
    external_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    external_image_url = models.URLField(max_length=500, blank=True, default='')
    # Désactivé plutôt que supprimé : ItemCommande.category est en CASCADE.
    is_active = models.BooleanField(default=True)
    # Heures (0-23, heure de Nouakchott) où l'article peut être commandé,
    # fournies par le catalogue partenaire (`hours`). Vide = toujours disponible.
    # Voir api/services/availability.py.
    available_hours = models.JSONField(default=list, blank=True)


    def __str__(self):
        return f'{self.name_fr} - {self.type}'





class LocationPoint(models.Model):
    """Point géographique pré-connu (quartier ou point de départ d'un provider).
    Pas de carte affichée au client : il choisit un quartier par son nom."""
    name = models.CharField(max_length=120, unique=True)
    name_ar = models.CharField(max_length=120, default='', blank=True)
    lat = models.FloatField()
    lng = models.FloatField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class DeliveryProvider(models.Model):
    """Partenaire de livraison (ex : Jemli). Chaque provider a son propre
    point de départ isolé (cuisine ou boutique partenaire)."""
    name = models.CharField(max_length=100, unique=True)
    code = models.SlugField(max_length=50, unique=True)
    # NB : le segment final ("10/2026") est un identifiant de route fourni par
    # JEMLI, qui a déjà changé une fois (voir api/services/jemli.py).
    base_url = models.URLField(default='https://api-jemli.oneposts.io/api/third-party/10/2026/')
    api_key = models.CharField(max_length=255, blank=True, default='')
    api_secret = models.CharField(max_length=255, blank=True, default='')
    origin_point = models.ForeignKey(
        LocationPoint, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='providers',
    )
    webhook_secret = models.CharField(max_length=64, blank=True, default='')
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.webhook_secret:
            self.webhook_secret = uuid.uuid4().hex
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class DeliveryType(models.Model):
    """Type d'article livrable (ex : mes_plats, poisson, l7am, sbou7).
    Correspond à Category.type par égalité de `code`. Un `provider` nul
    signifie livraison legacy (guewda / sayra / mechwi, calcul côté app)."""
    code = models.SlugField(max_length=50, unique=True)
    name_fr = models.CharField(max_length=100)
    name_ar = models.CharField(max_length=100, default='', blank=True)
    delivery_margin = models.FloatField(default=50)
    provider = models.ForeignKey(
        DeliveryProvider, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='delivery_types',
    )
    is_scheduled = models.BooleanField(
        default=False,
        help_text="Envoi différé au delivery_datetime choisi par le client (mes_plats).",
    )
    catalog_category = models.CharField(
        max_length=50, blank=True, default='',
        help_text="Catégorie du catalogue partenaire (ex : restaurant). Si renseignée, "
                  "les articles de ce type sont importés depuis le partenaire.",
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.code


class Commande(models.Model):
    STATUS_CHOICES = [
        ('waiting', 'Waiting'),
        ('paid', 'Paid'),
        ('looking_for_driver', 'Looking for driver'),
        # Étapes JEMLI d'une commande restaurant (orders/).
        ('vendor_confirmed', 'Vendor confirmed'),
        ('vendor_preparing', 'Vendor preparing'),
        ('ready_for_pickup', 'Ready for pickup'),
        ('driver_assigned', 'Driver assigned'),
        ('loading', 'Loading'),
        ('driver_collected', 'Driver collected'),
        ('driver_on_way', 'Driver on the way'),
        ('driver_arrived', 'Driver arrived'),
        ('delivered', 'Delivered'),
        ('rejected', 'Rejected'),
    ]

    DISPATCH_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('scheduled', 'Scheduled'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled by partner'),
    ]

    prix = models.FloatField()
    livraison = models.FloatField(default=0)
    title = models.CharField(max_length=100, default='', null=True)
    code = models.CharField(max_length=100, default='', unique=True, editable=False)
    date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting')
    location = models.TextField()
    phone = models.CharField(max_length=100, default='')
    avec_6begat = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    capture = CloudinaryField('image', blank=True, null=True)

    # --- Livraison via partenaire (Jemli & co) ---
    delivery_type = models.ForeignKey(
        DeliveryType, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='commandes',
    )
    delivery_provider = models.ForeignKey(
        DeliveryProvider, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='commandes',
    )
    location_point = models.ForeignKey(
        LocationPoint, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='commandes', help_text="Destination (quartier choisi par le client).",
    )
    # Point de livraison choisi sur la carte par le client (prioritaire sur
    # location_point, conservé pour les anciennes commandes).
    delivery_lat = models.FloatField(null=True, blank=True)
    delivery_lng = models.FloatField(null=True, blank=True)
    driver_phone = models.CharField(max_length=30, blank=True, default='')
    partner_delivery_ref = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Identifiant de la livraison renvoyé par le partenaire.",
    )
    partner_delivery_fee = models.FloatField(null=True, blank=True)
    delivery_final_price = models.FloatField(
        null=True, blank=True,
        help_text="partner_delivery_fee + delivery_type.delivery_margin — montant payé par le client.",
    )
    delivery_datetime = models.DateTimeField(
        null=True, blank=True,
        help_text="Moment de livraison choisi par le client (mes_plats).",
    )
    dispatch_status = models.CharField(
        max_length=20, choices=DISPATCH_STATUS_CHOICES, default='pending',
    )
    dispatched_at = models.DateTimeField(null=True, blank=True)
    # Dernier statut détaillé reçu du partenaire (ex. vendor_preparing) : plus
    # fin que `status`, qui reste dans la liste connue de l'app.
    partner_status = models.CharField(max_length=50, blank=True, default='')

    # Numéro du wallet avec lequel le client paie (peut différer de `phone`),
    # normalisé sur 8 chiffres : sert au rapprochement automatique TwizePay.
    payment_phone = models.CharField(max_length=20, blank=True, default='', db_index=True)

    # --- Montant (calculé par api/services/pricing.py à la création) ---
    service_fee = models.FloatField(default=0)
    promotion = models.ForeignKey(
        'Promotion', on_delete=models.SET_NULL, null=True, blank=True, related_name='commandes',
    )
    promo_code = models.CharField(max_length=30, blank=True, default='')
    discount_amount = models.FloatField(default=0, help_text="Remise sur le prix des articles.")
    delivery_discount = models.FloatField(default=0, help_text="Remise sur la livraison.")
    credit_used = models.FloatField(default=0, help_text="Crédit fidélité du client déduit.")

    @property
    def total_amount(self):
        """Montant que le client doit payer (rapproché des paiements TwizePay) :
        articles + livraison + frais de service - remises - crédit utilisé."""
        total = (
            (self.prix or 0) + (self.livraison or 0) + (self.service_fee or 0)
            - (self.discount_amount or 0) - (self.delivery_discount or 0) - (self.credit_used or 0)
        )
        return round(max(total, 0), 2)

    @property
    def destination(self):
        """Objet avec `.lat`/`.lng` : point choisi sur la carte, sinon quartier."""
        if self.delivery_lat is not None and self.delivery_lng is not None:
            return LocationPoint(lat=self.delivery_lat, lng=self.delivery_lng)
        return self.location_point

    def save(self, *args, **kwargs):
        if not self.code:
            unique_code = uuid.uuid4().hex[:8].upper()
            self.code = f"CM{unique_code}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Commande {self.id} - {self.status} - {self.title}"




class WalletTransaction(models.Model):
    """Transaction détectée par TwizePay sur un de nos wallets (webhook
    payments/webhook/twizepay/). Toutes sont conservées, entrées comme sorties."""
    DIRECTION_CHOICES = [('CR', 'Entrée'), ('DR', 'Sortie')]
    MATCH_STATUS_CHOICES = [
        ('pending', 'Non rapprochée'),
        ('matched', 'Rapprochée'),
        ('ignored', 'Ignorée'),
    ]

    external_id = models.CharField(max_length=64, unique=True, help_text="`id` TwizePay.")
    bank_reference = models.CharField(max_length=100, blank=True, default='', help_text="`transactionId` de la banque.")
    wallet = models.CharField(max_length=30, blank=True, default='')
    direction = models.CharField(max_length=2, choices=DIRECTION_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    counterparty_number = models.CharField(max_length=30, blank=True, default='')
    counterparty_name = models.CharField(max_length=150, blank=True, default='')
    payer_phone = models.CharField(
        max_length=20, blank=True, default='', db_index=True,
        help_text="counterparty_number normalisé sur 8 chiffres.",
    )
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_event_id = models.CharField(max_length=64, blank=True, default='')
    raw = models.JSONField(default=dict, blank=True)

    commande = models.ForeignKey(
        Commande, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments',
    )
    match_status = models.CharField(max_length=10, choices=MATCH_STATUS_CHOICES, default='pending')
    matched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-received_at']

    def __str__(self):
        return f"{self.wallet} {self.direction} {self.amount} MRU - {self.counterparty_number or '?'}"


class ItemCommande(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    commande = models.ForeignKey(Commande, on_delete=models.CASCADE, related_name='items')
    number = models.PositiveIntegerField()
    selected_price = models.FloatField(default=0)
    with_chicken = models.BooleanField(default=False, null=True, blank=True)
    chicken_number = models.PositiveIntegerField(default=0, null=True, blank=True)
    remplissage = models.CharField(max_length=100, default="", null=True, blank=True)

    def __str__(self):
        return f"ItemCommande {self.id} - x{self.number}"


class Poster(models.Model):
    image = CloudinaryField('image')


class AppConfiguration(models.Model):
    minimum_version_android = models.CharField(max_length=10, default="1.0.0")
    minimum_version_ios = models.CharField(max_length=10, default="1.0.0")
    force_update = models.BooleanField(default=True)
    store_url = models.URLField(default="https://play.google.com/store/apps/details?id=com.chwily.app")
    appstore_url = models.URLField(default="https://apps.apple.com/mr/app/chwily/id6747934029")

    # Frais de service ajoutés à chaque commande (0 = gratuit).
    service_fee = models.FloatField(default=0, help_text="Frais de service par commande, en MRU (0 = gratuit).")
    # Fidélité : toutes les `loyalty_orders_count` commandes livrées, le client
    # reçoit `loyalty_reward_amount` MRU de crédit, déduit de ses commandes suivantes.
    loyalty_enabled = models.BooleanField(default=False, verbose_name="Fidélité activée")
    loyalty_orders_count = models.PositiveIntegerField(
        default=10, help_text="Nombre de commandes livrées (X) pour gagner la récompense.",
    )
    loyalty_reward_amount = models.FloatField(
        default=0, help_text="Crédit (Y, en MRU) offert après X commandes livrées.",
    )

    @classmethod
    def current(cls):
        """La configuration (singleton), ou les valeurs par défaut si absente."""
        return cls.objects.first() or cls()

    class Meta:
        verbose_name = "Configuration de l'Application"

    def __str__(self):
        return "Configuration Globale"



class Promotion(models.Model):
    """Promotion sur une période : automatique pour tous les clients si `code`
    est vide, sinon appliquée quand le client saisit le code. Une seule
    promotion par commande (la plus avantageuse) — voir api/services/pricing.py."""
    DISCOUNT_TYPES = [
        ('amount', 'Montant fixe sur la commande'),
        ('percent', 'Pourcentage sur la commande'),
        ('free_delivery', 'Livraison gratuite'),
    ]

    name = models.CharField(max_length=100, verbose_name="Nom")
    code = models.CharField(
        max_length=30, blank=True, default='', db_index=True,
        help_text="Code promo à saisir par le client. Vide = promotion automatique pour tous.",
    )
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES, default='amount')
    value = models.FloatField(
        default=0, help_text="Montant en MRU (montant fixe) ou pourcentage (ex : 10). Ignoré pour la livraison gratuite.",
    )
    max_discount = models.FloatField(
        null=True, blank=True, help_text="Plafond de la remise en MRU (pourcentage uniquement). Vide = sans plafond.",
    )
    min_order_amount = models.FloatField(default=0, help_text="Prix minimum des articles pour en profiter.")
    starts_at = models.DateTimeField(verbose_name="Début")
    ends_at = models.DateTimeField(verbose_name="Fin")
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text="Utilisations au total. Vide = illimité.")
    max_uses_per_user = models.PositiveIntegerField(
        null=True, blank=True, help_text="Utilisations par client. Vide = illimité.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-starts_at']

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({'ends_at': "La fin doit être après le début."})
        if self.discount_type == 'percent' and not 0 < (self.value or 0) <= 100:
            raise ValidationError({'value': "Un pourcentage doit être entre 0 et 100."})
        if self.discount_type == 'amount' and (self.value or 0) <= 0:
            raise ValidationError({'value': "Le montant doit être positif."})
        code = (self.code or '').strip().upper()
        if code and Promotion.objects.filter(code=code).exclude(pk=self.pk).exists():
            raise ValidationError({'code': "Ce code existe déjà."})

    def save(self, *args, **kwargs):
        self.code = (self.code or '').strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.name} ({self.code})' if self.code else self.name


class CreditTransaction(models.Model):
    """Mouvement du crédit d'un client (récompense fidélité, geste manuel).
    Le solde = somme des mouvements - crédit engagé dans ses commandes
    (Commande.credit_used) : voir api/services/pricing.py."""
    KINDS = [
        ('loyalty_reward', 'Récompense fidélité'),
        ('manual', 'Ajustement manuel'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='credit_transactions')
    amount = models.FloatField(help_text="Positif = crédit offert, négatif = retrait.")
    kind = models.CharField(max_length=20, choices=KINDS, default='manual')
    commande = models.ForeignKey(
        Commande, on_delete=models.SET_NULL, null=True, blank=True, related_name='credit_rewards',
        help_text="Commande qui a déclenché la récompense.",
    )
    note = models.CharField(max_length=200, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} {self.amount:+} ({self.kind})'
