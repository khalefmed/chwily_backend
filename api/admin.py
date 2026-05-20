from django.contrib import admin
from api.models import *

# Register your models here.
admin.site.register(Category)
admin.site.register(Commande)
admin.site.register(User)
admin.site.register(ItemCommande)
admin.site.register(Poster)


admin.site.site_header = "Chwily Admin"
admin.site.site_title = "Chwily Admin Portal"
admin.site.index_title = "Welcome to Chwily Admin Portal"