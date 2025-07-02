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
    path('logout/', LogoutView.as_view(), name='logout'),
    path('signup/', SignupView.as_view(), name='signup'),
    path('check-phone/', check_phone_exists, name='check-phone'),
    path('update-lang/', update_default_lang),
    path('me/delete/', DeleteAccountView.as_view(), name='delete-account'),


    # Custom category views
    path('category/guewda/', GuewdaCategoryView.as_view(), name='category-guewda'),
    path('category/sayra/', SayraCategoryView.as_view(), name='category-sayra'),
    path('category/mechwi/', MechwiCategoryView.as_view(), name='category-mechwi'),

    # Commande-related views
    path('mes_commandes/', MesCommandesView.as_view(), name='mes-commandes'),
    path('commandes/add/', AddCommandeView.as_view(), name='add-commande'),
    path('commandes/pending/', PendingCommandesView.as_view(), name='pending-commandes'),  #done
    path('commandes/<int:pk>/change_status/', ChangeCommandeStatusView.as_view(), name='change-commande-status'),

    # User-related views
    path('update_password/', UpdatePasswordView.as_view(), name='update-password'),
    path('update_infos/', UpdateUserNameView.as_view(), name='update-infos'),
    path('me/', MeView.as_view(), name='me'),
    path('user/phone/<int:phone>/', GetUserByPhoneView.as_view(), name='get-user-by-phone'),
    path('users/<int:pk>/toggle_type/', ToggleUserTypeView.as_view(), name='toggle-user-type'),

    # Statistics
    path('stats/', StatisticsView.as_view(), name='stats'), #done

    # ViewSets
    path('', include(router.urls)),
]