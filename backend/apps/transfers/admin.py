from django.contrib import admin

from .models import Transfer, TransferStatusEvent


class TransferStatusEventInline(admin.TabularInline):
    model = TransferStatusEvent
    extra = 0
    readonly_fields = ("created_at", "updated_at")


@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "sender",
        "recipient",
        "send_amount",
        "source_currency",
        "receive_amount",
        "destination_currency",
        "status",
        "updated_at",
    )
    list_filter = ("status", "funding_status", "compliance_status", "payout_status")
    search_fields = ("reference", "sender__email", "recipient__first_name", "recipient__last_name")
    readonly_fields = ("reference", "created_at", "updated_at")
    inlines = [TransferStatusEventInline]


@admin.register(TransferStatusEvent)
class TransferStatusEventAdmin(admin.ModelAdmin):
    list_display = ("transfer", "from_status", "to_status", "changed_by", "created_at")
    list_filter = ("to_status",)
    search_fields = ("transfer__reference", "changed_by__email")
    readonly_fields = ("created_at", "updated_at")
