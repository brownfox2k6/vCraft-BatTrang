"""Domain service for public artisan household workshop applications (Pending)."""

import re
import uuid
from decimal import Decimal, InvalidOperation

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, Field

from app.core.security import Argon2PasswordHasher, validate_password_strength
from app.core.slugs import generate_unique_slug
from app.models.auth import UserRole
from app.models.media import MediaCategory
from app.models.workshop import WorkshopApplicationStatus
from app.repositories.auth_repository import AuthRepository, DuplicateEmailRepositoryError
from app.repositories.media_repository import MediaRepository
from app.repositories.workshop_application_repository import WorkshopApplicationRepository
from app.services.audit_service import AuditAction, AuditService

_PHONE_ALLOWED_RE = re.compile(r"^[0-9+\-\s().]{8,32}$")
_MAX_MEDIA_PER_GROUP = 10


class WorkshopApplicationInput(BaseModel):
    """JSON payload submitted by a household artisan on POST /api/workshop-applications."""

    artisan_name: str = ""
    email: str = ""
    phone: str = ""
    password: str = ""
    name_vi: str = ""
    name_en: str | None = None
    tagline_vi: str | None = None
    tagline_en: str | None = None
    address_vi: str = ""
    address_en: str | None = None
    history_vi: str = ""
    history_en: str | None = None
    opening_hours: str = ""
    is_open_now: bool = True
    has_experience: bool = False
    experience_desc_vi: str | None = None
    experience_desc_en: str | None = None
    latitude: float | str | None = None
    longitude: float | str | None = None
    workshop_media_ids: list[str] = Field(default_factory=list)
    certificate_media_ids: list[str] = Field(default_factory=list)


class WorkshopApplicationResult(BaseModel):
    """Payload returned after creating an inactive Artisan user + Pending application."""

    id: uuid.UUID
    application_code: str
    proposed_slug: str
    status: WorkshopApplicationStatus
    message: str


class WorkshopApplicationError(Exception):
    """Typed validation or conflict error carrying an API code and translation keys."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message_key: str,
        field_errors: dict[str, str] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message_key = message_key
        self.field_errors = field_errors or {}


def _clean_optional(value: str | None, *, max_length: int) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        return None
    return cleaned[:max_length]


def _clean_multiline(value: str | None, *, max_length: int = 5000) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:max_length]


def _normalize_email(raw_email: str) -> str | None:
    cleaned = raw_email.strip()
    if not cleaned:
        return None
    try:
        info = validate_email(cleaned, check_deliverability=False)
    except EmailNotValidError:
        return None
    return info.normalized.lower()


def _parse_coordinate(raw: float | str | None, *, minimum: int, maximum: int) -> Decimal | None:
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    try:
        dec = Decimal(str(raw).strip()).quantize(Decimal("0.000001"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid_coordinate") from exc
    if dec < Decimal(minimum) or dec > Decimal(maximum):
        raise ValueError("out_of_range")
    return dec


def _parse_uuid_list(raw_ids: list[str]) -> list[uuid.UUID] | None:
    parsed: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for raw in raw_ids:
        try:
            uid = uuid.UUID(str(raw).strip())
        except (ValueError, AttributeError):
            return None
        if uid not in seen:
            seen.add(uid)
            parsed.append(uid)
    return parsed


class WorkshopApplicationService:
    """Service orchestrating public workshop application validation and atomic submission."""

    def __init__(
        self,
        *,
        application_repository: WorkshopApplicationRepository,
        auth_repository: AuthRepository,
        media_repository: MediaRepository,
        password_hasher: Argon2PasswordHasher,
        audit_service: AuditService,
    ) -> None:
        self._applications = application_repository
        self._auth = auth_repository
        self._media = media_repository
        self._password_hasher = password_hasher
        self._audit = audit_service

    def _next_application_code(self) -> str:
        seq = self._applications.count_applications() + 1
        while True:
            candidate = f"APP-{seq:03d}"
            if not self._applications.application_code_exists(candidate):
                return candidate
            seq += 1

    def submit_application(
        self,
        payload: WorkshopApplicationInput,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        success_message: str = "",
    ) -> WorkshopApplicationResult:
        """Validate and create an inactive Artisan user + Pending application in one transaction."""
        field_errors: dict[str, str] = {}

        artisan_name = " ".join(payload.artisan_name.split())
        if len(artisan_name) < 2 or len(artisan_name) > 120:
            field_errors["artisan_name"] = "workshop_apply.errors.artisan_name_invalid"

        normalized_email = _normalize_email(payload.email)
        if normalized_email is None:
            field_errors["email"] = "auth.errors.email_invalid"

        phone = " ".join(payload.phone.split())
        digits_only = "".join(ch for ch in phone if ch.isdigit())
        if not _PHONE_ALLOWED_RE.fullmatch(phone) or len(digits_only) < 8 or len(digits_only) > 15:
            field_errors["phone"] = "workshop_apply.errors.phone_invalid"

        password_error = validate_password_strength(payload.password)
        if password_error is not None:
            field_errors["password"] = password_error

        name_vi = " ".join(payload.name_vi.split())
        if len(name_vi) < 2 or len(name_vi) > 160:
            field_errors["name_vi"] = "workshop_apply.errors.name_vi_invalid"

        address_vi = " ".join(payload.address_vi.split())
        if len(address_vi) < 5 or len(address_vi) > 255:
            field_errors["address_vi"] = "workshop_apply.errors.address_vi_invalid"

        history_vi = (payload.history_vi or "").strip()
        if len(history_vi) < 10 or len(history_vi) > 5000:
            field_errors["history_vi"] = "workshop_apply.errors.history_vi_invalid"

        opening_hours = " ".join(payload.opening_hours.split())
        if len(opening_hours) < 3 or len(opening_hours) > 80:
            field_errors["opening_hours"] = "workshop_apply.errors.opening_hours_invalid"

        latitude: Decimal | None = None
        longitude: Decimal | None = None
        try:
            latitude = _parse_coordinate(payload.latitude, minimum=-90, maximum=90)
        except ValueError:
            field_errors["latitude"] = "workshop_apply.errors.latitude_invalid"
        try:
            longitude = _parse_coordinate(payload.longitude, minimum=-180, maximum=180)
        except ValueError:
            field_errors["longitude"] = "workshop_apply.errors.longitude_invalid"

        if (
            "latitude" not in field_errors
            and "longitude" not in field_errors
            and (latitude is None) != (longitude is None)
        ):
            field_errors["latitude"] = "workshop_apply.errors.coordinates_pair_required"
            field_errors["longitude"] = "workshop_apply.errors.coordinates_pair_required"

        workshop_uuids = _parse_uuid_list(payload.workshop_media_ids)
        if not workshop_uuids or len(workshop_uuids) > _MAX_MEDIA_PER_GROUP:
            field_errors["workshop_media_ids"] = "workshop_apply.errors.workshop_media_required"

        certificate_uuids = _parse_uuid_list(payload.certificate_media_ids)
        if not certificate_uuids or len(certificate_uuids) > _MAX_MEDIA_PER_GROUP:
            field_errors["certificate_media_ids"] = (
                "workshop_apply.errors.certificate_media_required"
            )

        if field_errors:
            raise WorkshopApplicationError(
                status_code=422,
                code="VALIDATION_ERROR",
                message_key="auth.errors.validation_failed",
                field_errors=field_errors,
            )

        assert normalized_email is not None
        assert workshop_uuids is not None
        assert certificate_uuids is not None

        # Verify referenced media_assets exist, are unowned, and match expected categories
        all_media_ids = [*workshop_uuids, *certificate_uuids]
        assets_by_id = {a.id: a for a in self._media.get_assets_by_ids(all_media_ids)}

        for uid in workshop_uuids:
            asset = assets_by_id.get(uid)
            if (
                asset is None
                or asset.owner_user_id is not None
                or asset.category != MediaCategory.WORKSHOP.value
            ):
                field_errors["workshop_media_ids"] = "workshop_apply.errors.media_invalid"
                break

        for uid in certificate_uuids:
            asset = assets_by_id.get(uid)
            if (
                asset is None
                or asset.owner_user_id is not None
                or asset.category != MediaCategory.CERTIFICATE.value
            ):
                field_errors["certificate_media_ids"] = "workshop_apply.errors.media_invalid"
                break

        if field_errors:
            raise WorkshopApplicationError(
                status_code=422,
                code="VALIDATION_ERROR",
                message_key="auth.errors.validation_failed",
                field_errors=field_errors,
            )

        if self._auth.get_user_by_email(normalized_email) is not None:
            raise WorkshopApplicationError(
                status_code=409,
                code="EMAIL_ALREADY_REGISTERED",
                message_key="auth.errors.email_exists",
                field_errors={"email": "auth.errors.email_exists"},
            )

        password_hash = self._password_hasher.hash(payload.password)
        try:
            user = self._auth.create_user(
                email=normalized_email,
                full_name=artisan_name,
                password_hash=password_hash,
                role=UserRole.ARTISAN,
                is_active=False,
            )
        except DuplicateEmailRepositoryError as exc:
            raise WorkshopApplicationError(
                status_code=409,
                code="EMAIL_ALREADY_REGISTERED",
                message_key="auth.errors.email_exists",
                field_errors={"email": "auth.errors.email_exists"},
            ) from exc

        proposed_slug = generate_unique_slug(name_vi, self._applications.slug_exists)
        application_code = self._next_application_code()

        application = self._applications.create_application(
            application_code=application_code,
            user_id=user.id,
            proposed_slug=proposed_slug,
            name_vi=name_vi,
            name_en=_clean_optional(payload.name_en, max_length=160),
            tagline_vi=_clean_optional(payload.tagline_vi, max_length=240),
            tagline_en=_clean_optional(payload.tagline_en, max_length=240),
            artisan_name=artisan_name,
            phone=phone,
            address_vi=address_vi,
            address_en=_clean_optional(payload.address_en, max_length=255),
            history_vi=history_vi,
            history_en=_clean_multiline(payload.history_en),
            opening_hours=opening_hours,
            is_open_now=payload.is_open_now,
            has_experience=payload.has_experience,
            experience_desc_vi=_clean_multiline(payload.experience_desc_vi),
            experience_desc_en=_clean_multiline(payload.experience_desc_en),
            latitude=latitude,
            longitude=longitude,
            workshop_media_ids=[str(uid) for uid in workshop_uuids],
            certificate_media_ids=[str(uid) for uid in certificate_uuids],
        )

        claimed_count = self._media.assign_owner(all_media_ids, user.id)
        if claimed_count != len(all_media_ids):
            self._applications.rollback()
            raise WorkshopApplicationError(
                status_code=422,
                code="VALIDATION_ERROR",
                message_key="auth.errors.validation_failed",
                field_errors={
                    "workshop_media_ids": "workshop_apply.errors.media_invalid",
                    "certificate_media_ids": "workshop_apply.errors.media_invalid",
                },
            )
        self._audit.record(
            action=AuditAction.WORKSHOP_APPLICATION_SUBMITTED.value,
            actor_user_id=user.id,
            actor_email=user.email,
            target_type="workshop_application",
            target_id=application.application_code,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"proposed_slug": proposed_slug, "status": application.status},
            commit=False,
        )
        self._applications.commit()

        return WorkshopApplicationResult(
            id=application.id,
            application_code=application.application_code,
            proposed_slug=application.proposed_slug,
            status=WorkshopApplicationStatus(application.status),
            message=success_message,
        )
