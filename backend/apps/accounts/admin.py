from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import SenderDocument, SenderKycCheck, SenderProfile, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "is_staff", "is_active")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )
    readonly_fields = ("date_joined", "last_login")


@admin.register(SenderProfile)
class SenderProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "phone_number",
        "country",
        "kyc_status",
        "kyc_submitted_at",
        "updated_at",
    )
    list_filter = ("kyc_status", "country")
    search_fields = ("user__email", "phone_number")
    readonly_fields = (
        "created_at",
        "updated_at",
        "kyc_submitted_at",
        "kyc_reviewed_at",
    )


@admin.register(SenderDocument)
class SenderDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "sender_profile",
        "document_type",
        "status",
        "content_type",
        "file_size",
        "reviewed_by",
        "reviewed_at",
        "created_at",
    )
    list_filter = ("document_type", "status", "content_type")
    search_fields = ("sender_profile__user__email", "sha256_digest")
    readonly_fields = (
        "encrypted_file",
        "encrypted_original_filename",
        "content_type",
        "file_size",
        "sha256_digest",
        "created_at",
        "updated_at",
    )


@admin.register(SenderKycCheck)
class SenderKycCheckAdmin(admin.ModelAdmin):
    list_display = (
        "sender_profile",
        "provider_name",
        "status",
        "provider_reference",
        "submitted_at",
        "completed_at",
    )
    list_filter = ("provider_name", "status")
    search_fields = (
        "sender_profile__user__email",
        "provider_reference",
    )
    readonly_fields = (
        "sender_profile",
        "provider_name",
        "provider_reference",
        "status",
        "request_payload",
        "response_payload",
        "status_reason",
        "submitted_at",
        "completed_at",
        "error",
        "created_at",
        "updated_at",
    )
