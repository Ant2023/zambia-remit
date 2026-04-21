from django.contrib import admin

from .models import Recipient, RecipientBankAccount, RecipientMobileMoneyAccount


@admin.register(Recipient)
class RecipientAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "sender",
        "country",
        "phone_number",
        "verification_status",
        "updated_at",
    )
    list_filter = ("country", "verification_status")
    search_fields = ("first_name", "last_name", "phone_number", "sender__email")
    readonly_fields = (
        "created_at",
        "updated_at",
        "verification_submitted_at",
        "verification_reviewed_at",
    )


@admin.register(RecipientMobileMoneyAccount)
class RecipientMobileMoneyAccountAdmin(admin.ModelAdmin):
    list_display = ("recipient", "provider_name", "mobile_number", "is_default")
    list_filter = ("provider_name", "is_default")
    search_fields = ("recipient__first_name", "recipient__last_name", "mobile_number")
    readonly_fields = ("created_at", "updated_at")


@admin.register(RecipientBankAccount)
class RecipientBankAccountAdmin(admin.ModelAdmin):
    list_display = ("recipient", "bank_name", "account_number", "is_default")
    list_filter = ("bank_name", "is_default")
    search_fields = ("recipient__first_name", "recipient__last_name", "account_number")
    readonly_fields = ("created_at", "updated_at")
