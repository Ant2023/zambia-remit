from django.db import transaction
from rest_framework import serializers

from apps.countries.models import Country
from apps.countries.serializers import CountrySerializer
from common.choices import PayoutMethod

from .models import Recipient, RecipientBankAccount, RecipientMobileMoneyAccount


class RecipientMobileMoneyAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecipientMobileMoneyAccount
        fields = (
            "id",
            "provider_name",
            "mobile_number",
            "account_name",
            "is_default",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class RecipientBankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecipientBankAccount
        fields = (
            "id",
            "bank_name",
            "account_number",
            "account_name",
            "branch_name",
            "swift_code",
            "is_default",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class RecipientSerializer(serializers.ModelSerializer):
    country = CountrySerializer(read_only=True)
    country_id = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.filter(is_destination_enabled=True),
        source="country",
        write_only=True,
    )
    payout_method = serializers.ChoiceField(
        choices=PayoutMethod.choices,
        write_only=True,
        required=False,
    )
    mobile_money_account = RecipientMobileMoneyAccountSerializer(
        write_only=True,
        required=False,
    )
    bank_account = RecipientBankAccountSerializer(write_only=True, required=False)
    mobile_money_accounts = RecipientMobileMoneyAccountSerializer(
        many=True,
        read_only=True,
    )
    bank_accounts = RecipientBankAccountSerializer(many=True, read_only=True)

    class Meta:
        model = Recipient
        fields = (
            "id",
            "first_name",
            "last_name",
            "phone_number",
            "country",
            "country_id",
            "relationship_to_sender",
            "payout_method",
            "mobile_money_account",
            "bank_account",
            "mobile_money_accounts",
            "bank_accounts",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_country_id(self, country):
        if not country.is_destination_enabled:
            raise serializers.ValidationError(
                "Recipients can only be created in enabled destination countries.",
            )
        return country

    def validate(self, attrs):
        payout_method = attrs.pop("payout_method", None)
        mobile_money_account = attrs.get("mobile_money_account")
        bank_account = attrs.get("bank_account")

        if mobile_money_account and bank_account:
            raise serializers.ValidationError(
                {"payout_method": "Create one payout account type at a time."},
            )

        if payout_method == PayoutMethod.MOBILE_MONEY and not mobile_money_account:
            raise serializers.ValidationError(
                {"mobile_money_account": "Mobile money details are required."},
            )

        if payout_method == PayoutMethod.MOBILE_MONEY and bank_account:
            raise serializers.ValidationError(
                {"bank_account": "Do not send bank details for a mobile money recipient."},
            )

        if payout_method == PayoutMethod.BANK_DEPOSIT and not bank_account:
            raise serializers.ValidationError(
                {"bank_account": "Bank account details are required."},
            )

        if payout_method == PayoutMethod.BANK_DEPOSIT and mobile_money_account:
            raise serializers.ValidationError(
                {
                    "mobile_money_account": (
                        "Do not send mobile money details for a bank deposit recipient."
                    )
                },
            )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        mobile_money_data = validated_data.pop("mobile_money_account", None)
        bank_account_data = validated_data.pop("bank_account", None)

        recipient = Recipient.objects.create(sender=request.user, **validated_data)

        if mobile_money_data:
            mobile_money_data.setdefault("is_default", True)
            RecipientMobileMoneyAccount.objects.create(
                recipient=recipient,
                **mobile_money_data,
            )

        if bank_account_data:
            bank_account_data.setdefault("is_default", True)
            RecipientBankAccount.objects.create(
                recipient=recipient,
                **bank_account_data,
            )

        return recipient
