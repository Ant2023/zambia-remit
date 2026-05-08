from django.contrib import admin

from .models import OperationalAuditLog


@admin.register(OperationalAuditLog)
class OperationalAuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "action_name",
        "actor",
        "target_type",
        "target_reference",
        "previous_status",
        "new_status",
    )
    list_filter = ("action_name", "target_type", "created_at")
    search_fields = (
        "action_name",
        "actor__email",
        "target_id",
        "target_reference",
        "note",
    )
    readonly_fields = (
        "id",
        "actor",
        "action_name",
        "target_type",
        "target_id",
        "target_reference",
        "previous_status",
        "new_status",
        "note",
        "request_ip",
        "user_agent",
        "metadata",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
