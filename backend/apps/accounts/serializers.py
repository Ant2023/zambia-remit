from django.contrib.auth import authenticate, get_user_model, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from apps.countries.models import Country
from apps.countries.serializers import CountrySerializer
from .models import SenderProfile


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "is_staff",
            "date_joined",
        )
        read_only_fields = ("id", "is_staff", "date_joined")


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "password",
            "password_confirm",
            "first_name",
            "last_name",
        )
        read_only_fields = ("id",)

    def validate_email(self, value):
        email = User.objects.normalize_email(value)
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("A customer with this email exists.")
        return email

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."},
            )
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data.pop("password_confirm")
        return User.objects.create_user(password=password, **validated_data)


class CustomerLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        request = self.context.get("request")
        email = User.objects.normalize_email(attrs["email"])
        password = attrs["password"]
        user = authenticate(request=request, username=email, password=password)

        if not user:
            raise serializers.ValidationError(
                {"detail": "Invalid email or password."},
            )

        if not user.is_active:
            raise serializers.ValidationError(
                {"detail": "This account is inactive."},
            )

        if user.is_staff or user.is_superuser:
            raise serializers.ValidationError(
                {"detail": "Staff accounts must use Django admin."},
            )

        attrs["user"] = user
        return attrs


class StaffLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        request = self.context.get("request")
        email = User.objects.normalize_email(attrs["email"])
        password = attrs["password"]
        user = authenticate(request=request, username=email, password=password)

        if not user:
            raise serializers.ValidationError(
                {"detail": "Invalid email or password."},
            )

        if not user.is_active:
            raise serializers.ValidationError(
                {"detail": "This account is inactive."},
            )

        if not (user.is_staff or user.is_superuser):
            raise serializers.ValidationError(
                {"detail": "Staff access is required."},
            )

        attrs["user"] = user
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."},
            )

        try:
            user_id = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=user_id, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist) as exc:
            raise serializers.ValidationError(
                {"token": "This password reset link is invalid or expired."},
            ) from exc

        if user.is_staff or user.is_superuser:
            raise serializers.ValidationError(
                {"token": "This password reset link is invalid or expired."},
            )

        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError(
                {"token": "This password reset link is invalid or expired."},
            )

        password_validation.validate_password(attrs["password"], user)
        attrs["user"] = user
        return attrs


class SenderProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(
        source="user.first_name",
        max_length=150,
        required=True,
        allow_blank=False,
    )
    last_name = serializers.CharField(
        source="user.last_name",
        max_length=150,
        required=True,
        allow_blank=False,
    )
    phone_number = serializers.CharField(required=True, allow_blank=False)
    country = CountrySerializer(read_only=True)
    country_id = serializers.PrimaryKeyRelatedField(
        source="country",
        queryset=Country.objects.filter(is_sender_enabled=True),
        write_only=True,
        required=True,
    )
    is_complete = serializers.SerializerMethodField()
    kyc_status_display = serializers.CharField(
        source="get_kyc_status_display",
        read_only=True,
    )

    class Meta:
        model = SenderProfile
        fields = (
            "id",
            "user",
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "country",
            "country_id",
            "date_of_birth",
            "address_line_1",
            "address_line_2",
            "city",
            "region",
            "postal_code",
            "kyc_status",
            "kyc_status_display",
            "kyc_submitted_at",
            "kyc_reviewed_at",
            "kyc_review_note",
            "is_complete",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "user",
            "email",
            "country",
            "kyc_status",
            "kyc_status_display",
            "kyc_submitted_at",
            "kyc_reviewed_at",
            "kyc_review_note",
            "is_complete",
            "created_at",
            "updated_at",
        )

    def get_is_complete(self, obj):
        return obj.is_complete

    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", {})
        should_reopen_kyc = self.should_reopen_kyc_review(instance, user_data, validated_data)

        for field, value in user_data.items():
            setattr(instance.user, field, value)

        if user_data:
            instance.user.save(update_fields=list(user_data.keys()))

        instance = super().update(instance, validated_data)

        if should_reopen_kyc:
            instance.kyc_status = SenderProfile.KycStatus.NEEDS_REVIEW
            instance.kyc_reviewed_at = None
            instance.kyc_reviewed_by = None
            instance.kyc_review_note = "Sender profile details changed after verification."
            instance.save(
                update_fields=(
                    "kyc_status",
                    "kyc_reviewed_at",
                    "kyc_reviewed_by",
                    "kyc_review_note",
                    "updated_at",
                ),
            )

        return instance

    def should_reopen_kyc_review(self, instance, user_data, profile_data):
        if instance.kyc_status != SenderProfile.KycStatus.VERIFIED:
            return False

        user_changed = any(
            getattr(instance.user, field) != value
            for field, value in user_data.items()
        )
        profile_changed = any(
            getattr(instance, field) != value
            for field, value in profile_data.items()
        )
        return user_changed or profile_changed


class SenderKycReviewSerializer(serializers.Serializer):
    kyc_status = serializers.ChoiceField(
        choices=(
            SenderProfile.KycStatus.VERIFIED,
            SenderProfile.KycStatus.REJECTED,
            SenderProfile.KycStatus.NEEDS_REVIEW,
        ),
    )
    review_note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000,
    )

    def validate(self, attrs):
        status = attrs["kyc_status"]
        note = attrs.get("review_note", "").strip()

        if status in {
            SenderProfile.KycStatus.REJECTED,
            SenderProfile.KycStatus.NEEDS_REVIEW,
        } and not note:
            raise serializers.ValidationError(
                {"review_note": "Add a note when KYC is rejected or needs review."},
            )

        attrs["review_note"] = note
        return attrs
