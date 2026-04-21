from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import generics, permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SenderProfile
from .serializers import (
    CustomerLoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SenderKycReviewSerializer,
    SenderProfileSerializer,
    StaffLoginSerializer,
    UserRegistrationSerializer,
    UserSerializer,
)


User = get_user_model()
PASSWORD_RESET_RESPONSE = (
    "If that customer account exists, a password reset link has been sent."
)


class RegistrationView(generics.CreateAPIView):
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        SenderProfile.objects.get_or_create(user=user)
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = CustomerLoginSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        SenderProfile.objects.get_or_create(user=user)
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "user": UserSerializer(user).data,
            },
        )


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = User.objects.normalize_email(serializer.validated_data["email"])
        user = (
            User.objects.filter(email__iexact=email, is_active=True)
            .exclude(is_staff=True)
            .exclude(is_superuser=True)
            .first()
        )

        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = (
                f"{settings.FRONTEND_BASE_URL}/reset-password/confirm"
                f"?uid={uid}&token={token}"
            )
            send_mail(
                "Reset your Zambia Remit password",
                (
                    "Use this secure link to reset your Zambia Remit password:\n\n"
                    f"{reset_url}\n\n"
                    "If you did not request this, you can ignore this email."
                ),
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )

        return Response({"detail": PASSWORD_RESET_RESPONSE})


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=("password",))
        Token.objects.filter(user=user).delete()
        return Response({"detail": "Your password has been reset."})


class StaffLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = StaffLoginSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "user": UserSerializer(user).data,
            },
        )


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class SenderProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = SenderProfileSerializer

    def get_object(self):
        profile, _ = SenderProfile.objects.get_or_create(user=self.request.user)
        return profile


class SenderKycSubmitView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        profile, _ = SenderProfile.objects.get_or_create(user=request.user)

        if not profile.is_complete:
            return Response(
                {"detail": "Complete your sender profile before submitting KYC."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if profile.kyc_status == SenderProfile.KycStatus.PENDING:
            return Response(
                {"detail": "Your sender profile is already pending review."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if profile.kyc_status == SenderProfile.KycStatus.VERIFIED:
            return Response(
                {"detail": "Your sender profile is already verified."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile.submit_kyc()
        return Response(SenderProfileSerializer(profile).data)


class StaffSenderKycReviewView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, profile_id):
        profile = generics.get_object_or_404(
            SenderProfile.objects.select_related("user", "country"),
            id=profile_id,
        )
        serializer = SenderKycReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        next_status = serializer.validated_data["kyc_status"]
        if (
            next_status == SenderProfile.KycStatus.VERIFIED
            and not profile.is_complete
        ):
            return Response(
                {"detail": "Complete sender profile details before verification."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile.mark_kyc_reviewed(
            status=next_status,
            reviewed_by=request.user,
            note=serializer.validated_data["review_note"],
        )
        return Response(SenderProfileSerializer(profile).data)
