from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()
router.register('users', UserViewSet)
router.register('categories', CategoryViewSet)
router.register('commandes', CommandeViewSet)
router.register('items', ItemCommandeViewSet)

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),

    # Custom routes
    path('category/guewda/', GuewdaCategoryView.as_view(), name='category-guewda'),
    path('category/sayra/', SayraCategoryView.as_view(), name='category-sayra'),
    path('category/mechwi/', MechwiCategoryView.as_view(), name='category-mechwi'),

    path('mes_commandes/', MesCommandesView.as_view(), name='mes-commandes'),
    path('commandes/add/', AddCommandeView.as_view(), name='add-commande'),
    path('update_password/', UpdatePasswordView.as_view(), name='update-password'),
    path('update_infos/', UpdateUserNameView.as_view(), name='update-infos'),
    path('me/', MeView.as_view(), name='me'),

    # ViewSets
    path('', include(router.urls)),
]
