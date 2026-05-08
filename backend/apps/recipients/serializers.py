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
        read_only_fields = (
            "id",
            "verification_status",
            "verification_status_display",
            "verification_submitted_at",
            "verification_reviewed_at",
            "is_verification_ready",
            "created_at",
            "updated_at",
        )


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
    verification_status_display = serializers.CharField(
        source="get_verification_status_display",
        read_only=True,
    )
    is_verification_ready = serializers.SerializerMethodField()

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
            "verification_status",
            "verification_status_display",
            "verification_submitted_at",
            "verification_reviewed_at",
            "is_verification_ready",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def get_is_verification_ready(self, obj):
        return obj.is_verification_ready

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
        country = attrs.get("country")

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

        if (
            self.instance
            and country
            and country.id != self.instance.country_id
            and self.instance.transfers.exists()
        ):
            raise serializers.ValidationError(
                {
                    "country_id": (
                        "Recipients with submitted transfers cannot change country."
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

    @transaction.atomic
    def update(self, instance, validated_data):
        mobile_money_data = validated_data.pop("mobile_money_account", None)
        bank_account_data = validated_data.pop("bank_account", None)
        should_reopen_verification = self.should_reopen_verification_review(
            instance,
            validated_data,
            mobile_money_data,
            bank_account_data,
        )

        for field, value in validated_data.items():
            setattr(instance, field, value)

        instance.save()

        if mobile_money_data:
            self.upsert_mobile_money_account(instance, mobile_money_data)

        if bank_account_data:
            self.upsert_bank_account(instance, bank_account_data)

        if should_reopen_verification:
            instance.verification_status = Recipient.VerificationStatus.NEEDS_REVIEW
            instance.verification_reviewed_at = None
            instance.verification_reviewed_by = None
            instance.verification_review_note = (
                "Recipient details changed after verification."
            )
            instance.save(
                update_fields=(
                    "verification_status",
                    "verification_reviewed_at",
                    "verification_reviewed_by",
                    "verification_review_note",
                    "updated_at",
                ),
            )

        return instance

    def should_reopen_verification_review(
        self,
        instance,
        validated_data,
        mobile_money_data,
        bank_account_data,
    ):
        if instance.verification_status != Recipient.VerificationStatus.VERIFIED:
            return False

        material_fields = {"first_name", "last_name", "phone_number", "country"}
        recipient_changed = any(
            field in material_fields and getattr(instance, field) != value
            for field, value in validated_data.items()
        )
        payout_changed = bool(mobile_money_data or bank_account_data)
        return recipient_changed or payout_changed

    def upsert_mobile_money_account(self, recipient, account_data):
        account = (
            recipient.mobile_money_accounts.filter(is_default=True).first()
            or recipient.mobile_money_accounts.first()
        )
        account_data.setdefault("is_default", True)

        if account:
            for field, value in account_data.items():
                setattr(account, field, value)
            account.save()
            return account

        return RecipientMobileMoneyAccount.objects.create(
            recipient=recipient,
            **account_data,
        )

    def upsert_bank_account(self, recipient, account_data):
        account = (
            recipient.bank_accounts.filter(is_default=True).first()
            or recipient.bank_accounts.first()
        )
        account_data.setdefault("is_default", True)

        if account:
            for field, value in account_data.items():
                setattr(account, field, value)
            account.save()
            return account

        return RecipientBankAccount.objects.create(
            recipient=recipient,
            **account_data,
        )


class RecipientVerificationReviewSerializer(serializers.Serializer):
    verification_status = serializers.ChoiceField(
        choices=(
            Recipient.VerificationStatus.VERIFIED,
            Recipient.VerificationStatus.REJECTED,
            Recipient.VerificationStatus.NEEDS_REVIEW,
        ),
    )
    review_note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000,
    )

    def validate(self, attrs):
        status = attrs["verification_status"]
        note = attrs.get("review_note", "").strip()

        if status in {
            Recipient.VerificationStatus.REJECTED,
            Recipient.VerificationStatus.NEEDS_REVIEW,
        } and not note:
            raise serializers.ValidationError(
                {
                    "review_note": (
                        "Add a note when recipient verification is rejected or needs review."
                    )
                },
            )

        attrs["review_note"] = note
        return attrs
