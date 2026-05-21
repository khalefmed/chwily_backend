from django.contrib import admin
from api.models import *

# Register your models here.
admin.site.register(Category)
admin.site.register(Commande)
admin.site.register(User)
admin.site.register(ItemCommande)
admin.site.register(Poster)

@admin.register(AppConfiguration)
class AppConfigurationAdmin(admin.ModelAdmin):
    list_display = ('minimum_version_android', 'minimum_version_ios', 'force_update')

    def has_add_permission(self, request):
        if AppConfiguration.objects.exists():
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        return False

admin.site.site_header = "Chwily Admin"
admin.site.site_title = "Chwily Admin Portal"
admin.site.index_title = "Welcome to Chwily Admin Portal"