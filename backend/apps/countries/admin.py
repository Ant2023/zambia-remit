from django.contrib import admin

from .models import (
    CorridorPayoutMethod,
    CorridorPayoutProvider,
    Country,
    CountryCorridor,
    Currency,
    PayoutProvider,
)


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "minor_unit")
    search_fields = ("code", "name")
    ordering = ("code",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "iso_code",
        "currency",
        "is_sender_enabled",
        "is_destination_enabled",
    )
    list_filter = ("is_sender_enabled", "is_destination_enabled")
    search_fields = ("name", "iso_code")
    list_select_related = ("currency",)
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(CountryCorridor)
class CountryCorridorAdmin(admin.ModelAdmin):
    list_display = (
        "source_country",
        "destination_country",
        "source_currency",
        "destination_currency",
        "min_send_amount",
        "max_send_amount",
        "is_active",
    )
    list_filter = ("is_active", "source_country", "destination_country")
    list_select_related = (
        "source_country",
        "destination_country",
        "source_currency",
        "destination_currency",
    )
    ordering = ("source_country__name", "destination_country__name")
    search_fields = (
        "source_country__name",
        "source_country__iso_code",
        "destination_country__name",
        "destination_country__iso_code",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(PayoutProvider)
class PayoutProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "payout_method", "is_active")
    list_filter = ("payout_method", "is_active")
    search_fields = ("name", "code")
    ordering = ("payout_method", "name")
    readonly_fields = ("created_at", "updated_at")


class CorridorPayoutProviderInline(admin.TabularInline):
    model = CorridorPayoutProvider
    extra = 0
    fields = (
        "provider",
        "is_active",
        "priority",
        "min_send_amount",
        "max_send_amount",
    )
    autocomplete_fields = ("provider",)


@admin.register(CorridorPayoutMethod)
class CorridorPayoutMethodAdmin(admin.ModelAdmin):
    list_display = (
        "corridor",
        "payout_method",
        "is_active",
        "min_send_amount",
        "max_send_amount",
        "display_order",
    )
    list_filter = ("payout_method", "is_active", "corridor")
    list_select_related = (
        "corridor__source_country",
        "corridor__destination_country",
    )
    search_fields = (
        "corridor__source_country__name",
        "corridor__destination_country__name",
        "payout_method",
    )
    ordering = (
        "corridor__source_country__name",
        "corridor__destination_country__name",
        "display_order",
    )
    readonly_fields = ("created_at", "updated_at")
    inlines = (CorridorPayoutProviderInline,)


@admin.register(CorridorPayoutProvider)
class CorridorPayoutProviderAdmin(admin.ModelAdmin):
    list_display = (
        "corridor_payout_method",
        "provider",
        "is_active",
        "priority",
        "min_send_amount",
        "max_send_amount",
    )
    list_filter = (
        "is_active",
        "provider__payout_method",
        "corridor_payout_method__corridor",
    )
    list_select_related = (
        "corridor_payout_method__corridor__source_country",
        "corridor_payout_method__corridor__destination_country",
        "provider",
    )
    search_fields = (
        "provider__name",
        "provider__code",
        "corridor_payout_method__corridor__source_country__name",
        "corridor_payout_method__corridor__destination_country__name",
    )
    ordering = (
        "corridor_payout_method__corridor__source_country__name",
        "corridor_payout_method__corridor__destination_country__name",
        "priority",
    )
    readonly_fields = ("created_at", "updated_at")
