import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils.deconstruct import deconstructible
from django.utils.functional import cached_property
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from common.security import decrypt_text, encrypt_text
from common.models import BaseModel


def secure_document_upload_path(instance, filename: str) -> str:
    return f"sender_profiles/{instance.sender_profile_id}/{uuid.uuid4().hex}.bin"


@deconstructible(path="apps.accounts.models.SecureDocumentStorage")
class SecureDocumentStorage(FileSystemStorage):
    def _clear_cached_properties(self, setting, **kwargs):
        super()._clear_cached_properties(setting, **kwargs)
        if setting == "SECURE_DOCUMENT_STORAGE_ROOT":
            self.__dict__.pop("base_location", None)
            self.__dict__.pop("location", None)

    @cached_property
    def base_location(self):
        return settings.SECURE_DOCUMENT_STORAGE_ROOT

    @cached_property
    def base_url(self):
        return None


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("The email address must be set.")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField(_("email address"), unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self) -> str:
        return self.email


class SenderProfile(BaseModel):
    class KycStatus(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        PENDING = "pending", "Pending"
        NEEDS_REVIEW = "needs_review", "Needs review"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sender_profile",
    )
    phone_number = models.CharField(max_length=32, blank=True)
    country = models.ForeignKey(
        "countries.Country",
        on_delete=models.PROTECT,
        related_name="sender_profiles",
        null=True,
        blank=True,
    )
    date_of_birth = models.DateField(null=True, blank=True)
    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    kyc_status = models.CharField(
        max_length=24,
        choices=KycStatus.choices,
        default=KycStatus.NOT_STARTED,
    )
    kyc_submitted_at = models.DateTimeField(null=True, blank=True)
    kyc_reviewed_at = models.DateTimeField(null=True, blank=True)
    kyc_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_sender_profiles",
        null=True,
        blank=True,
    )
    kyc_review_note = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=("country", "kyc_status")),
            models.Index(fields=("kyc_status", "kyc_submitted_at")),
        ]

    @property
    def is_complete(self) -> bool:
        return bool(
            self.user.first_name
            and self.user.last_name
            and self.phone_number
            and self.country_id
        )

    def submit_kyc(self) -> None:
        self.kyc_status = self.KycStatus.PENDING
        self.kyc_submitted_at = timezone.now()
        self.kyc_reviewed_at = None
        self.kyc_reviewed_by = None
        self.kyc_review_note = ""
        self.save(
            update_fields=(
                "kyc_status",
                "kyc_submitted_at",
                "kyc_reviewed_at",
                "kyc_reviewed_by",
                "kyc_review_note",
                "updated_at",
            ),
        )

    def mark_kyc_reviewed(self, *, status: str, reviewed_by, note: str = "") -> None:
        self.kyc_status = status
        self.kyc_reviewed_at = timezone.now()
        self.kyc_reviewed_by = reviewed_by
        self.kyc_review_note = note
        self.save(
            update_fields=(
                "kyc_status",
                "kyc_reviewed_at",
                "kyc_reviewed_by",
                "kyc_review_note",
                "updated_at",
            ),
        )

    def __str__(self) -> str:
        return f"Profile for {self.user.email}"


class SenderDocument(BaseModel):
    class DocumentType(models.TextChoices):
        GOVERNMENT_ID = "government_id", "Government ID"
        PROOF_OF_ADDRESS = "proof_of_address", "Proof of address"
        SELFIE = "selfie", "Selfie"
        SOURCE_OF_FUNDS = "source_of_funds", "Source of funds"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        NEEDS_REVIEW = "needs_review", "Needs review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    sender_profile = models.ForeignKey(
        SenderProfile,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_sender_documents",
    )
    document_type = models.CharField(max_length=40, choices=DocumentType.choices)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.UPLOADED,
    )
    encrypted_file = models.FileField(
        upload_to=secure_document_upload_path,
        storage=SecureDocumentStorage(),
    )
    encrypted_original_filename = models.TextField()
    content_type = models.CharField(max_length=120)
    file_size = models.PositiveIntegerField()
    sha256_digest = models.CharField(max_length=64)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_sender_documents",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("sender_profile", "status")),
            models.Index(fields=("status", "created_at")),
            models.Index(fields=("document_type", "status")),
            models.Index(fields=("sha256_digest",)),
        ]
        permissions = [
            ("review_sender_document", "Can review sender verification documents"),
            ("download_sender_document", "Can download sender verification documents"),
        ]

    @property
    def original_filename(self) -> str:
        return decrypt_text(self.encrypted_original_filename)

    def set_original_filename(self, filename: str) -> None:
        self.encrypted_original_filename = encrypt_text(filename)

    def mark_reviewed(self, *, status: str, reviewed_by, note: str = "") -> None:
        self.status = status
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.review_note = note
        self.save(
            update_fields=(
                "status",
                "reviewed_by",
                "reviewed_at",
                "review_note",
                "updated_at",
            ),
        )

    def __str__(self) -> str:
        return f"{self.sender_profile.user.email}: {self.document_type}"
