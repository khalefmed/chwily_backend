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
    # NB : le segment final (ex. "28/08/2026") ressemble à une date mais n'en
    # est pas une — c'est un identifiant de route fixe propre au compte
    # partenaire (confirmé empiriquement, voir api/services/jemli.py).
    base_url = models.URLField(default='https://api-jemli.oneposts.io/api/third-party/28/08/2026/')
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
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.code


class Commande(models.Model):
    STATUS_CHOICES = [
        ('waiting', 'Waiting'),
        ('paid', 'Paid'),
        ('looking_for_driver', 'Looking for driver'),
        ('driver_assigned', 'Driver assigned'),
        ('loading', 'Loading'),
        ('delivered', 'Delivered'),
        ('rejected', 'Rejected'),
    ]

    DISPATCH_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('scheduled', 'Scheduled'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
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

    def save(self, *args, **kwargs):
        if not self.code:
            unique_code = uuid.uuid4().hex[:8].upper()
            self.code = f"CM{unique_code}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Commande {self.id} - {self.status} - {self.title}"




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

    class Meta:
        verbose_name = "Configuration de l'Application"

    def __str__(self):
        return "Configuration Globale"

