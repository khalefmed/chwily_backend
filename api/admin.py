from django.contrib import admin
from api.models import *

admin.site.register(User)
admin.site.register(ItemCommande)
admin.site.register(Poster)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name_fr', 'type', 'price1', 'order', 'is_active', 'external_id')
    list_filter = ('type', 'is_active')
    search_fields = ('name_fr', 'name_ar', 'external_id')


@admin.register(LocationPoint)
class LocationPointAdmin(admin.ModelAdmin):
    list_display = ('name', 'name_ar', 'lat', 'lng', 'is_active')
    list_editable = ('lat', 'lng', 'is_active')
    search_fields = ('name', 'name_ar')


@admin.register(DeliveryProvider)
class DeliveryProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'origin_point', 'is_active')
    readonly_fields = ('webhook_secret',)


@admin.register(DeliveryType)
class DeliveryTypeAdmin(admin.ModelAdmin):
    list_display = ('code', 'name_fr', 'name_ar', 'delivery_margin', 'provider', 'is_scheduled', 'catalog_category', 'is_active')
    list_editable = ('delivery_margin', 'provider', 'is_scheduled', 'catalog_category', 'is_active')


@admin.register(Commande)
class CommandeAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'title', 'status', 'total_amount', 'promotion', 'partner_status', 'dispatch_status', 'delivery_provider', 'delivery_datetime', 'date')
    list_filter = ('status', 'dispatch_status', 'delivery_provider', 'delivery_type')
    search_fields = ('code', 'phone', 'payment_phone', 'title')
    readonly_fields = ('code', 'date', 'total_amount')

@admin.register(AppConfiguration)
class AppConfigurationAdmin(admin.ModelAdmin):
    list_display = ('minimum_version_android', 'minimum_version_ios', 'force_update',
                    'service_fee', 'loyalty_enabled', 'loyalty_orders_count', 'loyalty_reward_amount')
    fieldsets = (
        ("Version de l'app", {'fields': ('minimum_version_android', 'minimum_version_ios', 'force_update',
                                         'store_url', 'appstore_url')}),
        ('Frais de service', {'fields': ('service_fee',)}),
        ('Fidélité', {
            'fields': ('loyalty_enabled', 'loyalty_orders_count', 'loyalty_reward_amount'),
            'description': "Toutes les X commandes livrées, le client reçoit Y MRU de crédit, "
                           "déduits automatiquement de ses commandes suivantes.",
        }),
    )

    def has_add_permission(self, request):
        if AppConfiguration.objects.exists():
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        return False

admin.site.site_header = "Chwily Admin"
admin.site.site_title = "Chwily Admin Portal"
admin.site.index_title = "Welcome to Chwily Admin Portal"

@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ('received_at', 'wallet', 'direction', 'amount', 'counterparty_number', 'counterparty_name',
                    'match_status', 'commande')
    list_filter = ('match_status', 'direction', 'wallet')
    search_fields = ('external_id', 'bank_reference', 'counterparty_number', 'payer_phone', 'commande__code')
    raw_id_fields = ('commande',)
    readonly_fields = [f.name for f in WalletTransaction._meta.fields if f.name not in ('commande', 'match_status')]


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'discount_type', 'value', 'starts_at', 'ends_at', 'is_active', 'uses')
    list_filter = ('is_active', 'discount_type')
    list_editable = ('is_active',)
    search_fields = ('name', 'code')
    fieldsets = (
        (None, {
            'fields': ('name', 'code', 'is_active'),
            'description': "Sans code : appliquée automatiquement à tous les clients pendant la période. "
                           "Une seule promotion par commande : la plus avantageuse.",
        }),
        ('Remise', {'fields': ('discount_type', 'value', 'max_discount', 'min_order_amount')}),
        ('Période', {'fields': ('starts_at', 'ends_at')}),
        ('Limites', {'fields': ('max_uses', 'max_uses_per_user')}),
    )

    @admin.display(description='Utilisations')
    def uses(self, obj):
        from api.services.pricing import engaged_commandes
        return engaged_commandes().filter(promotion=obj).count()


@admin.register(CreditTransaction)
class CreditTransactionAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'amount', 'kind', 'commande', 'note')
    list_filter = ('kind',)
    search_fields = ('user__phone', 'user__first_name', 'user__last_name', 'note')
    raw_id_fields = ('user', 'commande')
