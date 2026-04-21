from django.contrib import admin

from .models import ExchangeRate, FeeRule, Quote


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = (
        "corridor",
        "rate",
        "provider_name",
        "is_active",
        "effective_at",
        "expires_at",
    )
    list_filter = ("is_active", "provider_name", "corridor__destination_currency")
    search_fields = (
        "provider_name",
        "corridor__source_country__name",
        "corridor__destination_country__name",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(FeeRule)
class FeeRuleAdmin(admin.ModelAdmin):
    list_display = (
        "corridor",
        "payout_method",
        "min_amount",
        "max_amount",
        "fixed_fee",
        "percentage_fee",
        "is_active",
    )
    list_filter = ("payout_method", "is_active")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "sender",
        "source_currency",
        "destination_currency",
        "send_amount",
        "receive_amount",
        "status",
        "expires_at",
    )
    list_filter = ("status", "source_currency", "destination_currency")
    search_fields = ("sender__email",)
    readonly_fields = ("created_at", "updated_at")
