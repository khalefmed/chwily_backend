import random
from django.db import DatabaseError
import requests
from rest_framework import viewsets, generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken,  TokenError
from django.contrib.auth import authenticate
from .models import User, Category, Commande, ItemCommande
from .serializers import *
from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
import json

from firebase_admin import messaging
from .firebase_init import *


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class CommandeViewSet(viewsets.ModelViewSet):
    queryset = Commande.objects.all()
    serializer_class = CommandeSerializer


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

                data = {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),  # ✅ Add this line
                    'user': user_data,
                }

                return Response(data, status=status.HTTP_200_OK)

            return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        return Response({'detail': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


# --- Category details by type ---
class GuewdaCategoryView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        categories = Category.objects.filter(type='guewda').order_by('id')
        serializer = CategorySerializer(categories, many=True)
        data = serializer.data

        if request.user.is_authenticated:
            if getattr(request.user, 'type', None) == 'traitor':
                for item in data:
                    item['price1'] = round(item['price1'] * 0.8, 2)
                    item['price2'] = round(item['price2'] * 0.8, 2)
                    item['price3'] = round(item['price3'] * 0.8, 2)
        return Response(data)


class SayraCategoryView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        categories = Category.objects.filter(type='sayra').order_by('id')
        serializer = CategorySerializer(categories, many=True)
        data = serializer.data

        if request.user.is_authenticated:
            if getattr(request.user, 'type', None) == 'traitor':
                for item in data:
                    item['price1'] = round(item['price1'] * 0.8, 2)
                    item['price2'] = round(item['price2'] * 0.8, 2)
                    item['price3'] = round(item['price3'] * 0.8, 2)

        return Response(data)


class MechwiCategoryView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        categories = Category.objects.filter(type='mechwi').order_by('id')
        serializer = CategorySerializer(categories, many=True)
        data = serializer.data

        if request.user.is_authenticated:
            if getattr(request.user, 'type', None) == 'traitor':
                for item in data:
                    item['price1'] = round(item['price1'] * 0.8, 2)
                    item['price2'] = round(item['price2'] * 0.8, 2)
                    item['price3'] = round(item['price3'] * 0.8, 2)

        return Response(data)


# --- Mes Commandes ---
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


# --- Update infos ---
# views.py
class UpdateUserNameView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UpdateUserNameSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"detail": "Name updated successfully"})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# --- Me ---
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserDetailSerializer(request.user)
        return Response(serializer.data)
    





class PendingCommandesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        waiting = Commande.objects.filter(status='waiting')
        loading = Commande.objects.filter(status='loading')
        return Response({
            "waiting": CommandeSerializer(waiting, many=True).data,
            "loading": CommandeSerializer(loading, many=True).data
        })
    




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
        if new_status not in ['waiting', 'paid', 'loading', 'delivered', 'rejected']:
            return Response({'detail': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)

        commande = get_object_or_404(Commande, pk=pk)
        commande.status = new_status
        commande.save()

        print(request.user.fcm_token)
        user = request.user



        statuses = {
            'ar': {
                'waiting': 'قيد الانتظار',
                'paid': 'مدفوع',
                'loading': 'قيد المعالجة',
                'delivered': 'تم التوصيل',
                'rejected': 'مرفوض',
            },
            'fr' : {
                'waiting' : 'en attente',
                'paid' : 'paye',
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

    return Response({"otp_sent": code, "exists": exists})



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
        response.raise_for_status()  # Will raise an exception for HTTP error codes
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






################## FIREBASE CONFIG


def send_notification(title, body, token):

    print(token)
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        token=token,
    )

    try:
        if token != '':
            response = messaging.send(message)
            print("✅ Notification envoyée avec ID:", response)
    except Exception as e:
        print("❌ Erreur lors de l'envoi de la notification :", e)



def send_notifications_to_admins(title, body):
    title = title
    body = body

    admins = User.objects.filter(type__in=['admin', 'super_admin'])

    if admins :
        for admin in admins :
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                token=admin.fcm_token,  
            )

            if admin.fcm_token != '':
                response = messaging.send(message)
                print("Message envoyé avec ID:", response)



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


# @login_required
# def send_notification_view(request):
#     if request.method == 'POST':
#         form = NotificationForm(request.POST)
#         if form.is_valid():
#             title = form.cleaned_data['title']
#             body = form.cleaned_data['body']

#             message = messaging.Message(
#                 notification=messaging.Notification(title=title, body=body),
#                 topic='all-users'
#             )
#             messaging.send(message)
#             return render(request, 'core/send_notification.html', {'form': form, 'success': True})
#     else:
#         form = NotificationForm()
#     return render(request, 'core/send_notification.html', {'form': form})

