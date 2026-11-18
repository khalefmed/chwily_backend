from rest_framework.permissions import BasePermission


class IsAppAdmin(BasePermission):
    """Admins de l'app (User.type admin / super_admin) : écrans « Gestion »."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and getattr(user, 'type', None) in ('admin', 'super_admin'))
