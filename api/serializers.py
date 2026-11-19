from rest_framework import serializers
from .models import (
    Poster, User, Category, Commande, ItemCommande,
    LocationPoint, DeliveryType, DeliveryProvider,
    AppConfiguration, Promotion, ScheduledNotification,
)

class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True)


class UserSerializer(serializers.ModelSerializer):
    class Meta: 
        model = User
        fields = ['id', 'username', 'phone', 'first_name', 'last_name', 'type', 'default_lang', 'password']
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def create(self, validated_data):
        user = User(**validated_data)
        user.set_password(validated_data['password'])
        user.save()
        return user
    

class UpdateUserNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['first_name', 'last_name']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'


class CategoryDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name_fr', 'image', 'name_ar', 'price1', 'price2', 'price3', 'livraison', 'is_big_steak', 'type', 'type_class']


class LocationPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocationPoint
        fields = ['id', 'name', 'name_ar', 'lat', 'lng']


class DeliveryTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryType
        fields = ['code', 'name_fr', 'name_ar', 'delivery_margin', 'is_scheduled']


class UserDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'phone', 'type', 'first_name', 'last_name', ]


class ItemCommandeSerializer(serializers.ModelSerializer):
    category = CategoryDetailSerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True
    )

    class Meta:
        model = ItemCommande
        fields = [
            'id', 'commande', 'category', 'category_id', 'selected_price',
            'number', 'with_chicken', 'chicken_number', 'remplissage'
        ]

class CommandeSerializer(serializers.ModelSerializer):
    user = UserDetailSerializer(read_only=True)
    items = ItemCommandeSerializer(many=True, read_only=True)
    total_amount = serializers.FloatField(read_only=True)
    promotion_name = serializers.CharField(source='promotion.name', read_only=True, default=None)
    amount_due = serializers.FloatField(read_only=True)
    is_editable = serializers.BooleanField(read_only=True)
    order_type = serializers.CharField(read_only=True)
    delivery_type_code = serializers.CharField(source='delivery_type.code', read_only=True, default=None)

    class Meta:
        model = Commande
        fields = [
            'id', 'title', 'code', 'prix', 'date', 'status', 'location', 'livraison', 'capture', 'avec_6begat',
            'phone', 'user', 'items',
            'delivery_type', 'delivery_provider', 'location_point', 'delivery_lat', 'delivery_lng',
            'driver_phone',
            'partner_delivery_ref', 'partner_delivery_fee', 'delivery_final_price',
            'delivery_datetime', 'dispatch_status', 'dispatched_at', 'payment_phone', 'partner_status',
            'service_fee', 'promotion', 'promotion_name', 'promo_code', 'discount_amount', 'delivery_discount',
            'credit_used', 'total_amount',
            'paid_amount', 'amount_due', 'is_editable', 'order_type', 'items_edited_at', 'delivery_type_code',
        ]
        read_only_fields = [
            'delivery_type', 'delivery_provider', 'driver_phone', 'partner_delivery_ref',
            'partner_delivery_fee', 'delivery_final_price', 'dispatch_status', 'dispatched_at', 'partner_status',
            # Montant : calculé par api/services/pricing.py, jamais fourni par l'app.
            'service_fee', 'promotion', 'promo_code', 'discount_amount', 'delivery_discount', 'credit_used',
            'paid_amount', 'items_edited_at',
        ]

    def create(self, validated_data):
        user = self.context['user'] 
        return Commande.objects.create(user=user, **validated_data)
    


class PosterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Poster
        fields = '__all__'

# --- Écrans « Gestion » de l'app admin ---

class PromotionSerializer(serializers.ModelSerializer):
    uses = serializers.SerializerMethodField()

    class Meta:
        model = Promotion
        fields = [
            'id', 'name', 'code', 'discount_type', 'value', 'max_discount', 'min_order_amount',
            'starts_at', 'ends_at', 'max_uses', 'max_uses_per_user', 'is_active', 'uses', 'created_at',
        ]
        read_only_fields = ['created_at']

    def get_uses(self, obj):
        from .services.pricing import engaged_commandes
        return engaged_commandes().filter(promotion=obj).count()

    def validate(self, attrs):
        # Mêmes règles que l'admin Django (Promotion.clean).
        from django.core.exceptions import ValidationError as DjangoValidationError
        data = {f: getattr(self.instance, f) for f in self.Meta.fields
                if self.instance is not None and f not in ('uses', 'created_at')}
        data.update(attrs)
        data.pop('id', None)
        candidate = Promotion(pk=getattr(self.instance, 'pk', None), **data)
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)
        return attrs


class ScheduledNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduledNotification
        fields = ['id', 'title', 'body', 'send_at', 'status', 'sent_at', 'error', 'created_at']
        read_only_fields = ['status', 'sent_at', 'error', 'created_at']

    def validate_send_at(self, value):
        from django.utils import timezone
        if value <= timezone.now():
            raise serializers.ValidationError("La date d'envoi doit être dans le futur.")
        return value


class LoyaltyConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppConfiguration
        fields = ['loyalty_enabled', 'loyalty_orders_count', 'loyalty_reward_amount']

    def validate_loyalty_orders_count(self, value):
        if value < 1:
            raise serializers.ValidationError('Au moins 1 commande.')
        return value

    def validate_loyalty_reward_amount(self, value):
        if value < 0:
            raise serializers.ValidationError('Montant positif attendu.')
        return value
