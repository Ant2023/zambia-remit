from rest_framework import serializers

from .models import Country, CountryCorridor, Currency


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


class CountryCorridorSerializer(serializers.ModelSerializer):
    source_country = CountrySerializer(read_only=True)
    destination_country = CountrySerializer(read_only=True)
    source_currency = CurrencySerializer(read_only=True)
    destination_currency = CurrencySerializer(read_only=True)

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
        )
