"""Authentication service orchestrating Buyer registration, sessions, and audit events."""

import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel

from app.core.config import Settings
from app.core.redirects import resolve_safe_next
from app.core.security import (
    Argon2PasswordHasher,
    generate_csrf_token,
    generate_session_token,
    hash_session_token,
    validate_password_strength,
)
from app.models.auth import User, UserRole
from app.repositories.auth_repository import (
    AuthRepository,
    DuplicateEmailRepositoryError,
)
from app.services.audit_service import AuditAction, AuditService

FULL_NAME_MIN_LENGTH = 2
FULL_NAME_MAX_LENGTH = 120

ROLE_DEFAULT_REDIRECTS: dict[UserRole, str] = {
    UserRole.BUYER: "/",
    UserRole.ARTISAN: "/nghe-nhan",
    UserRole.ADMIN: "/quan-tri",
}


class AuthenticatedUser(BaseModel):
    """Public user representation returned in auth responses and template context."""

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole


class AuthResult(BaseModel):
    """Payload returned after successful registration or login."""

    user: AuthenticatedUser
    redirect_to: str


class MeResult(BaseModel):
    """Payload returned by GET /api/auth/me."""

    user: AuthenticatedUser


class LogoutResult(BaseModel):
    """Payload returned by POST /api/auth/logout."""

    logged_out: bool


@dataclass(frozen=True)
class SessionIssueResult:
    """Authenticated result paired with the opaque session cookie and bound CSRF token."""

    result: AuthResult
    raw_token: str
    csrf_token: str


@dataclass(frozen=True)
class SessionContext:
    """Active server-side session context attached to incoming HTTP requests."""

    session_id: uuid.UUID
    user: AuthenticatedUser
    csrf_token: str


class AuthError(Exception):
    """Base typed authentication error carrying an API code and translation key."""

    def __init__(
        self,
        *,
        code: str,
        message_key: str,
        status_code: int,
        field_errors: dict[str, str] | None = None,
        message_params: dict[str, object] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.message_key = message_key
        self.status_code = status_code
        self.field_errors = field_errors or {}
        self.message_params = message_params or {}


class ValidationAuthError(AuthError):
    """Raised when registration or login inputs fail validation rules."""

    def __init__(
        self,
        *,
        message_key: str = "auth.errors.validation_failed",
        field_errors: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            code="VALIDATION_ERROR",
            message_key=message_key,
            status_code=422,
            field_errors=field_errors,
        )


class DuplicateEmailAuthError(AuthError):
    """Raised when registering an email address that already exists."""

    def __init__(self) -> None:
        super().__init__(
            code="EMAIL_ALREADY_REGISTERED",
            message_key="auth.errors.email_exists",
            status_code=409,
            field_errors={"email": "auth.errors.email_exists"},
        )


class InvalidCredentialsAuthError(AuthError):
    """Raised when email or password verification fails."""

    def __init__(self) -> None:
        super().__init__(
            code="INVALID_CREDENTIALS",
            message_key="auth.errors.invalid_credentials",
            status_code=401,
        )


class AccountInactiveAuthError(AuthError):
    """Raised when a locked or inactive account attempts to authenticate."""

    def __init__(self) -> None:
        super().__init__(
            code="ACCOUNT_INACTIVE",
            message_key="auth.errors.account_inactive",
            status_code=403,
        )


class RateLimitExceededAuthError(AuthError):
    """Raised when failed login attempts exceed the configured sliding window."""

    def __init__(self, *, retry_after_seconds: int) -> None:
        minutes = max(1, math.ceil(retry_after_seconds / 60))
        super().__init__(
            code="RATE_LIMIT_EXCEEDED",
            message_key="auth.errors.rate_limited",
            status_code=429,
            message_params={"minutes": minutes},
        )
        self.retry_after_seconds = retry_after_seconds


def _to_authenticated_user(user: User) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=UserRole(user.role),
    )


def _normalize_and_validate_email(raw_email: str) -> str | None:
    cleaned = raw_email.strip()
    if not cleaned:
        return None
    try:
        info = validate_email(cleaned, check_deliverability=False)
    except EmailNotValidError:
        return None
    return info.normalized.lower()


def default_utc_clock() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class AuthService:
    """Domain service handling registration, session resolution, login, and logout."""

    def __init__(
        self,
        repository: AuthRepository,
        password_hasher: Argon2PasswordHasher,
        settings: Settings,
        clock: Callable[[], datetime] = default_utc_clock,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repository = repository
        self._password_hasher = password_hasher
        self._settings = settings
        self._clock = clock
        self._audit = audit_service

    def _record_audit(
        self,
        *,
        action: AuditAction,
        actor_user_id: uuid.UUID | None = None,
        actor_email: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        if self._audit is not None:
            self._audit.record(
                action=action.value,
                actor_user_id=actor_user_id,
                actor_email=actor_email,
                target_type=target_type,
                target_id=target_id,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details,
                commit=False,
            )

    def register_buyer(
        self,
        *,
        full_name: str,
        email: str,
        password: str,
        next_url: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> SessionIssueResult:
        """Validate inputs, create an active Buyer account, and issue a server session."""
        field_errors: dict[str, str] = {}

        cleaned_name = " ".join(full_name.split())
        if len(cleaned_name) < FULL_NAME_MIN_LENGTH or len(cleaned_name) > FULL_NAME_MAX_LENGTH:
            field_errors["full_name"] = "auth.errors.full_name_invalid"

        normalized_email = _normalize_and_validate_email(email)
        if normalized_email is None:
            field_errors["email"] = "auth.errors.email_invalid"

        password_error_key = validate_password_strength(password)
        if password_error_key is not None:
            field_errors["password"] = password_error_key

        if field_errors:
            raise ValidationAuthError(field_errors=field_errors)

        assert normalized_email is not None
        if self._repository.get_user_by_email(normalized_email) is not None:
            raise DuplicateEmailAuthError

        password_hash = self._password_hasher.hash(password)
        try:
            user = self._repository.create_user(
                email=normalized_email,
                full_name=cleaned_name,
                password_hash=password_hash,
                role=UserRole.BUYER,
                is_active=True,
            )
        except DuplicateEmailRepositoryError as exc:
            raise DuplicateEmailAuthError from exc

        return self._issue_session_for_user(
            user=user,
            next_url=next_url,
            ip_address=ip_address,
            user_agent=user_agent,
            audit_action=AuditAction.AUTH_REGISTER,
        )

    def login(
        self,
        *,
        email: str,
        password: str,
        next_url: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> SessionIssueResult:
        """Authenticate Buyer, Artisan, or Admin credentials and issue a session."""
        field_errors: dict[str, str] = {}
        normalized_email = _normalize_and_validate_email(email)
        if normalized_email is None:
            field_errors["email"] = "auth.errors.email_invalid"
        if not password:
            field_errors["password"] = "auth.errors.password_required"
        if field_errors:
            raise ValidationAuthError(field_errors=field_errors)

        assert normalized_email is not None
        now = self._clock()
        window_seconds = self._settings.login_rate_limit_window_seconds
        window_start = now - timedelta(seconds=window_seconds)
        scope_key = f"{ip_address or 'unknown'}|{normalized_email}"[:320]

        self._repository.prune_stale_attempts(window_start)
        recent_attempts = self._repository.count_recent_attempts(scope_key, window_start)
        if recent_attempts >= self._settings.login_rate_limit_max_attempts:
            oldest = self._repository.get_oldest_attempt_in_window(scope_key, window_start)
            retry_after = window_seconds
            if oldest is not None:
                if oldest.tzinfo is None:
                    oldest = oldest.replace(tzinfo=UTC)
                remaining = math.ceil(
                    (oldest + timedelta(seconds=window_seconds) - now).total_seconds()
                )
                retry_after = max(1, remaining)
            self._record_audit(
                action=AuditAction.AUTH_LOGIN_FAILED,
                actor_email=normalized_email,
                target_type="auth",
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "rate_limited"},
            )
            self._repository.commit()
            raise RateLimitExceededAuthError(retry_after_seconds=retry_after)

        user = self._repository.get_user_by_email(normalized_email)
        if user is None:
            self._password_hasher.verify_dummy(password)
            self._repository.record_failed_attempt(scope_key, now)
            self._record_audit(
                action=AuditAction.AUTH_LOGIN_FAILED,
                actor_email=normalized_email,
                target_type="auth",
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "unknown_email"},
            )
            self._repository.commit()
            raise InvalidCredentialsAuthError

        if not self._password_hasher.verify(user.password_hash, password):
            self._repository.record_failed_attempt(scope_key, now)
            self._record_audit(
                action=AuditAction.AUTH_LOGIN_FAILED,
                actor_user_id=user.id,
                actor_email=user.email,
                target_type="user",
                target_id=str(user.id),
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "invalid_password"},
            )
            self._repository.commit()
            raise InvalidCredentialsAuthError

        if not user.is_active:
            self._record_audit(
                action=AuditAction.AUTH_LOGIN_FAILED,
                actor_user_id=user.id,
                actor_email=user.email,
                target_type="user",
                target_id=str(user.id),
                ip_address=ip_address,
                user_agent=user_agent,
                details={"reason": "account_inactive"},
            )
            self._repository.commit()
            raise AccountInactiveAuthError

        self._repository.clear_attempts(scope_key)
        if self._password_hasher.needs_rehash(user.password_hash):
            self._repository.update_password_hash(user, self._password_hasher.hash(password))

        return self._issue_session_for_user(
            user=user,
            next_url=next_url,
            ip_address=ip_address,
            user_agent=user_agent,
            audit_action=AuditAction.AUTH_LOGIN_SUCCESS,
        )

    def logout(
        self,
        raw_token: str | None,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> LogoutResult:
        """Delete the server-side session matching the cookie token and record audit log."""
        if raw_token and raw_token.strip():
            token_hash = hash_session_token(raw_token.strip())
            existing = self._repository.get_session_by_token_hash(token_hash)
            if existing is not None:
                self._record_audit(
                    action=AuditAction.AUTH_LOGOUT,
                    actor_user_id=existing.user.id,
                    actor_email=existing.user.email,
                    target_type="session",
                    target_id=str(existing.id),
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                self._repository.delete_session(existing)
                self._repository.commit()
        return LogoutResult(logged_out=True)

    def resolve_session_context(self, raw_token: str | None) -> SessionContext | None:
        """Resolve an active, unexpired session cookie to its user and bound CSRF token."""
        if not raw_token or not raw_token.strip():
            return None

        token_hash = hash_session_token(raw_token.strip())
        user_session = self._repository.get_session_by_token_hash(token_hash)
        if user_session is None:
            return None

        now = self._clock()
        expires_at = user_session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        if expires_at <= now or not user_session.user.is_active:
            self._repository.delete_session(user_session)
            self._repository.commit()
            return None

        return SessionContext(
            session_id=user_session.id,
            user=_to_authenticated_user(user_session.user),
            csrf_token=user_session.csrf_token,
        )

    def resolve_session(self, raw_token: str | None) -> AuthenticatedUser | None:
        """Resolve an active, unexpired session cookie to an authenticated user."""
        context = self.resolve_session_context(raw_token)
        return context.user if context is not None else None

    def _issue_session_for_user(
        self,
        *,
        user: User,
        next_url: str | None,
        ip_address: str | None,
        user_agent: str | None,
        audit_action: AuditAction,
    ) -> SessionIssueResult:
        raw_token = generate_session_token()
        csrf_token = generate_csrf_token()
        token_hash = hash_session_token(raw_token)
        expires_at = self._clock() + timedelta(seconds=self._settings.session_ttl_seconds)

        session_row = self._repository.create_session(
            user_id=user.id,
            token_hash=token_hash,
            csrf_token=csrf_token,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self._record_audit(
            action=audit_action,
            actor_user_id=user.id,
            actor_email=user.email,
            target_type="user" if audit_action == AuditAction.AUTH_REGISTER else "session",
            target_id=str(user.id if audit_action == AuditAction.AUTH_REGISTER else session_row.id),
            ip_address=ip_address,
            user_agent=user_agent,
            details={"role": user.role},
        )
        self._repository.commit()

        role = UserRole(user.role)
        redirect_to = resolve_safe_next(next_url, default=ROLE_DEFAULT_REDIRECTS[role])
        return SessionIssueResult(
            result=AuthResult(
                user=_to_authenticated_user(user),
                redirect_to=redirect_to,
            ),
            raw_token=raw_token,
            csrf_token=csrf_token,
        )
