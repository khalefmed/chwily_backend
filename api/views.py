from rest_framework import viewsets, generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
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

        print('The token form request is : {fcm_token}') 

        user = User.objects.filter(phone=phone).first()

        if user:
            user = authenticate(request, phone=phone, password=password)
            if user:
                if fcm_token:
                    print('in fcm_token')
                    user.fcm_token = fcm_token
                    user.save(update_fields=['fcm_token'])

                print('The users token now is : {user.fcm_token}')
                refresh = RefreshToken.for_user(user)
                user_data = UserDetailSerializer(user).data

                data = {
                    'token': str(refresh.access_token),
                    'user': user_data,
                }
                

                return Response(data, status=status.HTTP_200_OK)

            return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        return Response({'detail': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


# --- Category details by type ---
class GuewdaCategoryView(APIView):
    def get(self, request):
        categories = Category.objects.filter(type='guewda').order_by('id')
        serializer = CategorySerializer(categories, many=True)
        data = serializer.data

        if hasattr(request.user, 'type') and request.user.type == 'traitor':
            for item in data:
                item['price1'] = round(item['price1'] * 0.8, 2)
                item['price2'] = round(item['price2'] * 0.8, 2)
                item['price3'] = round(item['price3'] * 0.8, 2)

        return Response(data)


class SayraCategoryView(APIView):
    def get(self, request):
        categories = Category.objects.filter(type='sayra').order_by('id')
        serializer = CategorySerializer(categories, many=True)
        data = serializer.data

        if hasattr(request.user, 'type') and request.user.type == 'traitor':
            for item in data:
                item['price1'] = round(item['price1'] * 0.8, 2)
                item['price2'] = round(item['price2'] * 0.8, 2)
                item['price3'] = round(item['price3'] * 0.8, 2)

        return Response(data)


class MechwiCategoryView(APIView):
    def get(self, request):
        categories = Category.objects.filter(type='mechwi').order_by('id')
        serializer = CategorySerializer(categories, many=True)
        data = serializer.data

        if hasattr(request.user, 'type') and request.user.type == 'traitor':
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

        # Prepare data dict for serializer, including the image file if present
        commande_data = {
            'prix': request.data.get('prix'),
            'location': request.data.get('location'),
            'livraison': request.data.get('livraison'),
            'location': request.data.get('location'),
            'phone': request.data.get('phone'),
            'user': request.user.id,
            'title': request.data.get('title'),
        }

        # Check if an image was uploaded and add it to the data
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
        

        send_notifications_to_admins(f'New Command', f'An new command added by {commande.phone} with code {commande.code}')


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
        if new_status not in ['waiting', 'paid', 'loading', 'delivered']:
            return Response({'detail': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)

        commande = get_object_or_404(Commande, pk=pk)
        commande.status = new_status
        commande.save()

        print(request.user.fcm_token)
                
        send_notification(
            'Status changed', 
            f'Commande {commande.code} - {commande.phone} is now {commande.status}',
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



@api_view(['POST'])
@permission_classes([AllowAny])
def check_phone_exists(request):
    phone = request.data.get('phone')

    if phone is None:
        return Response({"error": "Phone number is required."}, status=status.HTTP_400_BAD_REQUEST)

    exists = User.objects.filter(phone=phone).exists()
    return Response({"exists": exists})












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

            response = messaging.send(message)
            print("Message envoyé avec ID:", response)



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

