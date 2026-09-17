from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()
router.register('users', UserViewSet)
router.register('categories', CategoryViewSet)
router.register('commandes', CommandeViewSet)
router.register('items', ItemCommandeViewSet)
router.register('posters', PosterViewSet)

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('signup/', SignupView.as_view(), name='signup'),
    path('check-phone/', check_phone_exists, name='check-phone'),
    path('update-lang/', update_default_lang),
    path('me/delete/', DeleteAccountView.as_view(), name='delete-account'),
    path('reset-password/', reset_password, name='reset_password'),

    path('category/<str:type>/', CategoryByTypeView.as_view(), name='category-by-type'),

    path('mes_commandes/', MesCommandesView.as_view(), name='mes-commandes'),
    path('commandes/add/', AddCommandeView.as_view(), name='add-commande'),
    path('commandes/delivery-quote/', DeliveryQuoteView.as_view(), name='delivery-quote'),
    path('commandes/status/<str:status_value>/', CommandesByStatusView.as_view(), name='commandes-by-status'),
    path('commandes/<int:pk>/change_status/', ChangeCommandeStatusView.as_view(), name='change-commande-status'),

    path('location-points/', LocationPointListView.as_view(), name='location-points'),
    path('delivery/webhook/<str:provider_code>/', DeliveryWebhookView.as_view(), name='delivery-webhook'),


    path('posters/', PosterViewSet.as_view({'get': 'list', 'post': 'create', 'put': 'update', 'delete': 'destroy'}), name='poster-list'),

    path('notifications/', send_notifications, name='send-notifications'),

    path('update_password/', UpdatePasswordView.as_view(), name='update-password'),
    path('update_infos/', UpdateUserNameView.as_view(), name='update-infos'),
    path('me/', MeView.as_view(), name='me'),
    path('user/phone/<int:phone>/', GetUserByPhoneView.as_view(), name='get-user-by-phone'),
    path('users/<int:pk>/toggle_type/', ToggleUserTypeView.as_view(), name='toggle-user-type'),

    path('stats/', StatisticsView.as_view(), name='stats'),

    path('', include(router.urls)),
]