from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers

from apps.countries.models import Country
from apps.countries.serializers import CountrySerializer
from .models import SenderProfile


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "date_joined")
        read_only_fields = ("id", "date_joined")


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
            "is_complete",
            "created_at",
            "updated_at",
        )

    def get_is_complete(self, obj):
        return bool(
            obj.user.first_name
            and obj.user.last_name
            and obj.phone_number
            and obj.country_id
        )

    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", {})

        for field, value in user_data.items():
            setattr(instance.user, field, value)

        if user_data:
            instance.user.save(update_fields=list(user_data.keys()))

        return super().update(instance, validated_data)
