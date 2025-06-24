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
        extra_fields.setdefault('username', phone)  # Ajout de username par défaut
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(phone, password, **extra_fields)

    def create_user(self, phone, password=None, **extra_fields):
        extra_fields.setdefault('username', phone)  # Ajout de username par défaut
        
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

    def __str__(self):
        return f'{self.name_fr} - {self.type}'





class Commande(models.Model):
    STATUS_CHOICES = [
        ('waiting', 'Waiting'),
        ('paid', 'Paid'),
        ('rejected', 'Rejected'),
        ('loading', 'Loading'),
        ('delivered', 'Delivered'),
    ]

    prix = models.FloatField()
    livraison = models.FloatField(default=0)
    title = models.CharField(max_length=100, default='')  
    code = models.CharField(max_length=100, default='', unique=True, editable=False)
    date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting')
    location = models.TextField()
    phone = models.CharField(max_length=100, default='') 
    avec_6begat = models.BooleanField(default=False) 
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    capture = CloudinaryField('image', blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.code:
            # Generate a short unique identifier (8 characters from UUID)
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




