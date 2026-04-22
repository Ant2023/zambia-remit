from rest_framework import permissions


class IsStaffWithRequiredPermissions(permissions.BasePermission):
    message = "Staff access with the required role permission is required."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active or not user.is_staff:
            return False

        if user.is_superuser:
            return True

        required_permissions = tuple(getattr(view, "required_permissions", ()))
        if not required_permissions:
            return True

        return user.has_perms(required_permissions)
