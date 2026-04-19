from django.contrib import admin

from .models import Country, CountryCorridor, Currency


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
