from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers

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
    class Meta:
        model = SenderProfile
        fields = (
            "id",
            "user",
            "phone_number",
            "country",
            "date_of_birth",
            "address_line_1",
            "address_line_2",
            "city",
            "region",
            "postal_code",
            "kyc_status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user", "kyc_status", "created_at", "updated_at")
