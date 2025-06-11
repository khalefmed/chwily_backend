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

        user = User.objects.filter(phone=phone).first()

        if user:
            user = authenticate(request, phone=phone, password=password)
            if user:
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
        categories = Category.objects.filter(type='guewda')
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
        categories = Category.objects.filter(type='sayra')
        serializer = CategorySerializer(categories, many=True)
        return Response(serializer.data)


class MechwiCategoryView(APIView):
    def get(self, request):
        categories = Category.objects.filter(type='mechwi')
        serializer = CategorySerializer(categories, many=True)
        return Response(serializer.data)


# --- Mes Commandes ---
class MesCommandesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        commandes = Commande.objects.filter(user=request.user)
        serializer = CommandeSerializer(commandes, many=True)
        return Response(serializer.data)


# --- Ajouter une commande ---
class AddCommandeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        items_data = request.data.get('items')
        if not items_data or not isinstance(items_data, list):
            return Response({'detail': 'A list of items is required.'}, status=status.HTTP_400_BAD_REQUEST)

        commande_data = {
            'prix': request.data.get('prix'),
            'location': request.data.get('location'),
            'phone': request.data.get('phone'),
            'user': request.user.id
        }

        commande_serializer = CommandeSerializer(data=commande_data)
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

        return Response(CommandeSerializer(commande).data, status=status.HTTP_201_CREATED)



# --- Update password ---
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
