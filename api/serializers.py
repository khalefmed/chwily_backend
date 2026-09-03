from rest_framework import serializers
from .models import (
    Poster, User, Category, Commande, ItemCommande,
    LocationPoint, DeliveryType, DeliveryProvider,
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

    class Meta:
        model = Commande
        fields = [
            'id', 'title', 'code', 'prix', 'date', 'status', 'location', 'livraison', 'capture', 'avec_6begat',
            'phone', 'user', 'items',
            'delivery_type', 'delivery_provider', 'location_point', 'driver_phone',
            'partner_delivery_ref', 'partner_delivery_fee', 'delivery_final_price',
            'delivery_datetime', 'dispatch_status', 'dispatched_at',
        ]
        read_only_fields = [
            'delivery_type', 'delivery_provider', 'driver_phone', 'partner_delivery_ref',
            'partner_delivery_fee', 'delivery_final_price', 'dispatch_status', 'dispatched_at',
        ]

    def create(self, validated_data):
        user = self.context['user'] 
        return Commande.objects.create(user=user, **validated_data)
    


class PosterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Poster
        fields = '__all__'