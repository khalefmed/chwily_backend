from logging import config
import random
from django.db import DatabaseError
import requests
from rest_framework import viewsets, generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken,  TokenError
from django.contrib.auth import authenticate
from .models import (
    AppConfiguration, User, Category, Commande, ItemCommande,
    DeliveryProvider, DeliveryType, LocationPoint,
)
from .serializers import *
from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
import json

from firebase_admin import messaging
from .firebase_init import *
from firebase_admin._messaging_utils import UnregisteredError
import logging.config

from .services.notifications import send_notification, send_notifications_to_admins
from .services.delivery import (
    dispatch_commande, resolve_delivery_type, quote_delivery, apply_partner_status,
)
from .services.jemli import DeliveryPartnerError

logger = logging.getLogger(__name__)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class CommandeViewSet(viewsets.ModelViewSet):
    queryset = Commande.objects.all()
    serializer_class = CommandeSerializer

class PosterViewSet(viewsets.ModelViewSet):
    queryset = Poster.objects.all()
    permission_classes = [AllowAny]
    serializer_class = PosterSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser)


class ItemCommandeViewSet(viewsets.ModelViewSet):
    queryset = ItemCommande.objects.all()
    serializer_class = ItemCommandeSerializer


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data['phone']
        password = serializer.validated_data['password']
        fcm_token = request.data.get('fcm_token') 

        print(f'The token from request is: {fcm_token}') 

        user = User.objects.filter(phone=phone).first()

        if user:
            user = authenticate(request, phone=phone, password=password)
            if user:
                if fcm_token:
                    print('Saving fcm_token...')
                    user.fcm_token = fcm_token
                    user.save(update_fields=['fcm_token'])

                print(f'The user\'s token now is: {user.fcm_token}')
                refresh = RefreshToken.for_user(user)
                user_data = UserDetailSerializer(user).data
                app_config = AppConfiguration.objects.first()

                data = {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                    "minimum_version": "1.0.3",
                    "latest_version": "1.0.3",
                    "latest_version_ios": "1.0.3",
                    "latest_version_android": "1.0.3",

                    "minimum_version_ios": app_config.minimum_version_ios if app_config else "1.0.0",
                    "minimum_version_android": app_config.minimum_version_android if app_config else "1.0.0",
                    "force_update": app_config.force_update if app_config else False,
                    "store_url": app_config.store_url if app_config else "https://play.google.com/store/apps/details?id=com.chwily.app",
                    "appstore_url": app_config.appstore_url if app_config else "https://apps.apple.com/mr/app/chwily/id6747934029",
                    'user': user_data,
                }

                return Response(data, status=status.HTTP_200_OK)

            return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        return Response({'detail': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


class GuewdaCategoryView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        categories = Category.objects.filter(type='guewda').order_by('order')
        serializer = CategorySerializer(categories, many=True)
        data = serializer.data

        if request.user.is_authenticated:
            if getattr(request.user, 'type', None) == 'traitor':
                for item in data:
                    item['price1'] = round(item['price1'] * 0.95, 2)
                    item['price2'] = round(item['price2'] * 0.95, 2)
                    item['price3'] = round(item['price3'] * 0.95, 2)
        return Response(data)


class SayraCategoryView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        categories = Category.objects.filter(type='sayra').order_by('order')
        serializer = CategorySerializer(categories, many=True)
        data = serializer.data

        if request.user.is_authenticated:
            if getattr(request.user, 'type', None) == 'traitor':
                for item in data:
                    item['price1'] = round(item['price1'] * 0.95, 2)
                    item['price2'] = round(item['price2'] * 0.95, 2)
                    item['price3'] = round(item['price3'] * 0.95, 2)

        return Response(data)


class MechwiCategoryView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        categories = Category.objects.filter(type='mechwi').order_by('order')
        serializer = CategorySerializer(categories, many=True)
        data = serializer.data

        if request.user.is_authenticated:
            if getattr(request.user, 'type', None) == 'traitor':
                for item in data:
                    item['price1'] = round(item['price1'] * 0.95, 2)
                    item['price2'] = round(item['price2'] * 0.95, 2)
                    item['price3'] = round(item['price3'] * 0.95, 2)

        return Response(data)
    

class PoissonCategoryView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        categories = Category.objects.filter(type='poisson').order_by('order')
        serializer = CategorySerializer(categories, many=True)
        data = serializer.data

        if request.user.is_authenticated:
            if getattr(request.user, 'type', None) == 'traitor':
                for item in data:
                    item['price1'] = round(item['price1'] * 0.95, 2)
                    item['price2'] = round(item['price2'] * 0.95, 2)
                    item['price3'] = round(item['price3'] * 0.95, 2)

        return Response(data)



class MesPlatsCategoryView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        categories = Category.objects.filter(type='mes_plats').order_by('order')
        serializer = CategorySerializer(categories, many=True)
        data = serializer.data

        if request.user.is_authenticated:
            if getattr(request.user, 'type', None) == 'traitor':
                for item in data:
                    item['price1'] = round(item['price1'] * 0.95, 2)
                    item['price2'] = round(item['price2'] * 0.95, 2)
                    item['price3'] = round(item['price3'] * 0.95, 2)

        return Response(data)


class MesCommandesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        commandes = Commande.objects.filter(user=request.user)
        serializer = CommandeSerializer(commandes, many=True)
        return Response(serializer.data)


class AddCommandeView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        items_data = request.data.get('items')
        if not items_data:
            return Response({'detail': 'A list of items is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            items_data = json.loads(items_data)
        except Exception:
            return Response({'detail': 'Items must be a valid JSON list.'}, status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(items_data, list):
            return Response({'detail': 'A list of items is required.'}, status=status.HTTP_400_BAD_REQUEST)


        print(request.data.get('livraison'))
        commande_data = {
            'prix': request.data.get('prix'),
            'location': request.data.get('location'),
            'livraison': request.data.get('livraison'),
            'phone': request.data.get('phone'),
            'user': request.user.id,
            'title': request.data.get('title'),
        }

        # Livraison partenaire (optionnel : renseigné par l'app pour les
        # types sbou7 / poisson / l7am / mes_plats).
        if request.data.get('location_point'):
            commande_data['location_point'] = request.data.get('location_point')
        if request.data.get('delivery_datetime'):
            commande_data['delivery_datetime'] = request.data.get('delivery_datetime')

        if 'capture' in request.FILES:
            commande_data['capture'] = request.FILES['capture']

        commande_serializer = CommandeSerializer(data=commande_data, context={'user': request.user})
        if not commande_serializer.is_valid():
            return Response({
                'detail': 'Invalid commande data.',
                'errors': commande_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        commande = commande_serializer.save()

        for item in items_data:
            item['commande'] = commande.id
            item_serializer = ItemCommandeSerializer(data=item)
            if not item_serializer.is_valid():
                commande.delete()
                return Response({
                    'detail': 'Invalid item data.',
                    'errors': item_serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

            item_serializer.save()

        # Résolution du type de livraison partenaire + prix (best-effort,
        # non bloquant). Le prix vient du devis fait par l'app au checkout.
        try:
            delivery_type = resolve_delivery_type(commande)
            if delivery_type is not None:
                commande.delivery_type = delivery_type
                commande.delivery_provider = delivery_type.provider
                fee = request.data.get('partner_delivery_fee')
                final = request.data.get('delivery_final_price')
                if fee not in (None, ''):
                    commande.partner_delivery_fee = float(fee)
                if final not in (None, ''):
                    commande.delivery_final_price = float(final)
                commande.save(update_fields=[
                    'delivery_type', 'delivery_provider',
                    'partner_delivery_fee', 'delivery_final_price',
                ])
        except Exception:
            logger.exception('Résolution livraison partenaire échouée pour %s', commande.code)

        user = request.user

        if user.default_lang == 'ar' :
            send_notifications_to_admins('طلب جديد', f'تمت إضافة طلب جديد من الرقم {commande.phone} بالكود {commande.code}')
        else :
            send_notifications_to_admins(f'Nouvelle commande', f'Nouvelle commande ajoutee par {commande.phone} avec le code {commande.code}')


        return Response(CommandeSerializer(commande).data, status=status.HTTP_201_CREATED)


class UpdatePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        old_password = request.data.get("old_password")
        new_password = request.data.get("new_password")

        if not request.user.check_password(old_password):
            return Response({"detail": "Old password is incorrect"}, status=status.HTTP_400_BAD_REQUEST)

        request.user.set_password(new_password)
        request.user.save()
        return Response({"detail": "Password updated successfully"})


class UpdateUserNameView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UpdateUserNameSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"detail": "Name updated successfully"})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserDetailSerializer(request.user)
        return Response(serializer.data)
    





class CommandesByStatusPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class CommandesByStatusView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = CommandesByStatusPagination

    def get(self, request, status_value):
        if getattr(request.user, 'type', None) not in ['admin', 'super_admin']:
            return Response({'detail': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)

        valid_statuses = dict(Commande.STATUS_CHOICES)
        if status_value not in valid_statuses:
            return Response(
                {'detail': f"Invalid status. Must be one of: {', '.join(valid_statuses)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        commandes = Commande.objects.filter(status=status_value) \
            .select_related('user') \
            .prefetch_related('items__category') \
            .order_by('-date')

        search = request.query_params.get('search')
        if search:
            commandes = commandes.filter(
                Q(phone__icontains=search) |
                Q(user__phone__icontains=search) |
                Q(code__icontains=search)
            )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(commandes, request)
        serializer = CommandeSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
    




class GetUserByPhoneView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, phone):
        try:
            user = User.objects.get(phone=phone)
            if user.type in ['simple', 'traitor']:
                return Response(UserDetailSerializer(user).data)
            else:
                return Response({"detail": "Not a simple or traitor user"}, status=status.HTTP_403_FORBIDDEN)
        except User.DoesNotExist:
            return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        




class StatisticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = {
            "simple_users": User.objects.filter(type='simple').count(),
            "traitors": User.objects.filter(type='traitor').count(),
            "commandes_delivered": Commande.objects.filter(status='delivered').count(),
            "commandes_waiting": Commande.objects.filter(status='waiting').count(),
            "commandes_loading": Commande.objects.filter(status='loading').count(),
        }
        return Response(data)
    




class ChangeCommandeStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        new_status = request.data.get('status')
        if new_status not in ['waiting', 'paid', 'looking_for_driver', 'driver_assigned', 'loading', 'delivered', 'rejected']:
            return Response({'detail': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)

        commande = get_object_or_404(Commande, pk=pk)
        commande.status = new_status
        commande.save(update_fields=['status'])

        # Au passage à "payé" : envoi (ou planification) vers le partenaire de
        # livraison. dispatch_commande peut faire évoluer le statut lui-même
        # (et notifie alors le client de son côté).
        dispatch_changed = False
        if new_status == 'paid':
            try:
                dispatch_commande(commande)
                dispatch_changed = commande.status != 'paid'
            except Exception:
                logger.exception('dispatch_commande a échoué pour %s', commande.code)

        if dispatch_changed:
            return Response({'detail': 'Status updated successfully', 'commande': CommandeSerializer(commande).data})

        user = commande.user

        statuses = {
            'ar': {
                'waiting': 'قيد الانتظار',
                'paid': 'مدفوع',
                'looking_for_driver': 'جاري البحث عن موصّل',
                'driver_assigned': 'تم تعيين موصّل',
                'loading': 'قيد المعالجة',
                'delivered': 'تم التوصيل',
                'rejected': 'مرفوض',
            },
            'fr' : {
                'waiting' : 'en attente',
                'paid' : 'paye',
                'looking_for_driver' : "recherche d'un livreur",
                'driver_assigned' : 'livreur assigne',
                'loading' : 'en cours',
                'delivered' : 'livre',
                'rejected' : 'rejecte',
            }
        }


                
        if user.default_lang == 'ar' :
            send_notification(
                statuses['ar'][commande.status], 
                f'تم تغيير حالة طلبك {commande.code}',
                commande.user.fcm_token
            )
        else :
            send_notification(
                statuses['fr'][commande.status], 
                f'Votre commande {commande.code} a change de status ',
                commande.user.fcm_token
            )
        return Response({'detail': 'Status updated successfully', 'commande': CommandeSerializer(commande).data})


class LocationPointListView(generics.ListAPIView):
    """Quartiers pré-connus (avec coordonnées) proposés au client au checkout."""
    permission_classes = [AllowAny]
    serializer_class = LocationPointSerializer
    pagination_class = None

    def get_queryset(self):
        return LocationPoint.objects.filter(is_active=True).order_by('name')


class DeliveryQuoteView(APIView):
    """Devis de livraison partenaire, appelé au checkout avant le paiement.

    Body : { "location_point": <id>, "delivery_type": "<code>" }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        lp_id = request.data.get('location_point')
        type_code = request.data.get('delivery_type')

        if not lp_id or not type_code:
            return Response(
                {'detail': 'location_point et delivery_type sont requis.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        destination = get_object_or_404(LocationPoint, pk=lp_id, is_active=True)
        delivery_type = get_object_or_404(DeliveryType, code=type_code, is_active=True)
        if delivery_type.provider is None:
            return Response(
                {'detail': "Ce type d'article ne passe pas par un partenaire de livraison."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            quote = quote_delivery(delivery_type, destination)
        except DeliveryPartnerError as exc:
            logger.warning('Devis JEMLI indisponible : %s', exc)
            return Response({'detail': f'Devis indisponible : {exc}'}, status=status.HTTP_502_BAD_GATEWAY)

        quote.pop('raw', None)
        return Response(quote)


class DeliveryWebhookView(APIView):
    """Reçoit les mises à jour de statut d'un partenaire de livraison.

    URL  : /api/delivery/webhook/<provider_code>/
    Auth : en-tête `X-Webhook-Secret` (ou `?secret=`) == provider.webhook_secret
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, provider_code):
        provider = get_object_or_404(DeliveryProvider, code=provider_code, is_active=True)

        secret = request.headers.get('X-Webhook-Secret') or request.query_params.get('secret')
        if not provider.webhook_secret or secret != provider.webhook_secret:
            return Response({'detail': 'Invalid webhook secret.'}, status=status.HTTP_403_FORBIDDEN)

        data = request.data or {}
        # TODO(jemli-doc) : ajuster les clés au vrai payload webhook JEMLI.
        ref = str(
            data.get('delivery_id') or data.get('id') or data.get('reference') or ''
        ).strip()
        external_status = data.get('status') or data.get('state')
        driver = data.get('driver')
        if isinstance(driver, dict):
            driver_phone = driver.get('phone') or driver.get('phone_number')
        else:
            driver_phone = data.get('driver_phone')

        if not ref:
            return Response({'detail': 'delivery_id manquant.'}, status=status.HTTP_400_BAD_REQUEST)

        commande = Commande.objects.filter(
            partner_delivery_ref=ref, delivery_provider=provider,
        ).first()
        if commande is None:
            return Response({'detail': 'Commande introuvable pour cette référence.'},
                            status=status.HTTP_404_NOT_FOUND)

        changed = apply_partner_status(commande, external_status, driver_phone)
        return Response({'detail': 'ok', 'status': commande.status, 'changed': changed})


class ToggleUserTypeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)

        if user.type == 'simple':
            user.type = 'traitor'
        elif user.type == 'traitor':
            user.type = 'simple'
        else:
            return Response({"detail": "Only 'simple' or 'traitor' users can be toggled."}, status=status.HTTP_400_BAD_REQUEST)

        user.save()
        return Response({"detail": "User type updated successfully", "new_type": user.type})





class SignupView(APIView):

    permission_classes = [AllowAny] 

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "message": "User created successfully",
                "user": UserDetailSerializer(user).data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



def generate_otp():
    return str(random.randint(100000, 999999))

@api_view(['POST'])
@permission_classes([AllowAny])
def check_phone_exists(request):
    phone = request.data.get('phone')
    purpose = request.data.get('purpose') 

    if phone is None or purpose not in ['signup', 'forgot_password']:
        return Response(
            {"error": "Phone and valid purpose ('signup' or 'forgot_password') are required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    exists = User.objects.filter(phone=phone).exists()

    if purpose == 'signup' and not exists:
        code = generate_otp()
        send_validation_sms(phone, code)
        return Response({"otp_sent": code, "exists": False})

    elif purpose == 'forgot_password' and exists:
        code = generate_otp()
        send_validation_sms(phone, code)
        return Response({"otp_sent": code, "exists": True})

    return Response({"otp_sent": None, "exists": exists})



@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password(request):
    phone = request.data.get('phone')
    new_password = request.data.get('new_password')

    if not phone or not new_password:
        return Response(
            {"error": "Phone number and new password are required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user = User.objects.get(phone=phone)
        user.set_password(new_password)
        user.save()
        return Response({"success": "Password updated successfully."}, status=status.HTTP_200_OK)

    except User.DoesNotExist:
        return Response({"error": "User with this phone number does not exist."}, status=status.HTTP_404_NOT_FOUND)


class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user
        try:
            user.delete()
            return Response({"detail": "Account deleted successfully."}, status=status.HTTP_204_NO_CONTENT)
        except DatabaseError as e:
            return Response(
                {"detail": "An error occurred while deleting the account.", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



def send_validation_sms(phone_number: str, code: str):
    url = 'https://chinguisoft.com/api/sms/validation/wQepFqCYVt3y40Ff'
    headers = {
        'Validation-token': 'MnQK3bW88JD5KPPUzeB5DDxuU4RwXT71',
        'Content-Type': 'application/json'
    }
    payload = {
        "phone": phone_number,
        "lang": "fr",
        "code": code
    }
    print('otp code')
    print(code)

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        print("Message sent successfully:", response.json())
        return response.json()
    except requests.exceptions.HTTPError as errh:
        print("HTTP Error:", errh)
    except requests.exceptions.ConnectionError as errc:
        print("Connection Error:", errc)
    except requests.exceptions.Timeout as errt:
        print("Timeout Error:", errt)
    except requests.exceptions.RequestException as err:
        print("Request Error:", err)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_notifications(request):
    title = request.data.get('title')
    body = request.data.get('body')

    if not title or not body:
        return Response(
            {"error": "Le titre et le message sont requis."}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data={
            "click_action": "FLUTTER_NOTIFICATION_CLICK",
            "type": "broadcast"
        },
        topic='all-users',
    )

    try:
        response = messaging.send(message)
        return Response({
            "success": "Notification envoyée avec succès.",
            "message_id": response
        }, status=status.HTTP_200_OK)

    except Exception as e:
        print(f"❌ Erreur FCM: {str(e)}")
        return Response(
            {"error": "Une erreur est survenue lors de l'envoi."}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )






@api_view(['POST'])
@permission_classes([AllowAny])
def test_notification(request):
    title = request.data.get('title')
    body = request.data.get('body')
    token = request.data.get('token')

    try:
        send_notification(title, body, token)
        return Response({"success": "Notification sent successfully."}, status=status.HTTP_200_OK)
    except Exception as e :
        return Response({'error' : e}, status=500)



# send_notification / send_notifications_to_admins : voir api/services/notifications.py


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")

        if not refresh_token:
            return Response({"detail": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()

            request.user.fcm_token = ""
            request.user.save(update_fields=["fcm_token"])

            return Response({"detail": "Successfully logged out."}, status=status.HTTP_205_RESET_CONTENT)

        except TokenError:
            return Response({"detail": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)
        



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_default_lang(request):
    user = request.user 
    new_lang = request.data.get('default_lang')

    if new_lang not in ['fr', 'ar']:  
        return Response({"error": "Langue invalide."}, status=status.HTTP_400_BAD_REQUEST)

    user.default_lang = new_lang
    user.save()

    return Response({
        "message": "Langue par défaut mise à jour avec succès.",
        "default_lang": user.default_lang
    }, status=status.HTTP_200_OK)

