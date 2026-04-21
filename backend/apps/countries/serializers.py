from rest_framework import serializers

from .models import (
    CorridorPayoutMethod,
    CorridorPayoutProvider,
    Country,
    CountryCorridor,
    Currency,
    PayoutProvider,
)


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = ("id", "code", "name", "minor_unit")


class CountrySerializer(serializers.ModelSerializer):
    currency = CurrencySerializer(read_only=True)

    class Meta:
        model = Country
        fields = (
            "id",
            "name",
            "iso_code",
            "dialing_code",
            "currency",
            "is_sender_enabled",
            "is_destination_enabled",
        )


class PayoutProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayoutProvider
        fields = ("id", "code", "name", "payout_method", "is_active")


class CorridorPayoutProviderSerializer(serializers.ModelSerializer):
    provider = PayoutProviderSerializer(read_only=True)

    class Meta:
        model = CorridorPayoutProvider
        fields = (
            "id",
            "provider",
            "is_active",
            "priority",
            "min_send_amount",
            "max_send_amount",
        )


class CorridorPayoutMethodSerializer(serializers.ModelSerializer):
    providers = serializers.SerializerMethodField()

    class Meta:
        model = CorridorPayoutMethod
        fields = (
            "id",
            "payout_method",
            "is_active",
            "min_send_amount",
            "max_send_amount",
            "display_order",
            "providers",
        )

    def get_providers(self, obj):
        providers = getattr(obj, "active_providers", None)
        if providers is None:
            providers = (
                obj.providers.select_related("provider")
                .filter(is_active=True, provider__is_active=True)
                .order_by("priority", "provider__name")
            )
        return CorridorPayoutProviderSerializer(providers, many=True).data


class CountryCorridorSerializer(serializers.ModelSerializer):
    source_country = CountrySerializer(read_only=True)
    destination_country = CountrySerializer(read_only=True)
    source_currency = CurrencySerializer(read_only=True)
    destination_currency = CurrencySerializer(read_only=True)
    payout_methods = serializers.SerializerMethodField()

    class Meta:
        model = CountryCorridor
        fields = (
            "id",
            "source_country",
            "destination_country",
            "source_currency",
            "destination_currency",
            "is_active",
            "min_send_amount",
            "max_send_amount",
            "payout_methods",
        )

    def get_payout_methods(self, obj):
        payout_methods = getattr(obj, "active_payout_methods", None)
        if payout_methods is None:
            payout_methods = (
                obj.payout_methods.filter(is_active=True)
                .prefetch_related("providers__provider")
                .order_by("display_order", "payout_method")
            )
        return CorridorPayoutMethodSerializer(payout_methods, many=True).data
