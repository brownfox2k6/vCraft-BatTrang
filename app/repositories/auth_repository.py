"""Authentication repository managing users, server-side sessions, and login attempts."""

import uuid
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.auth import LoginAttempt, User, UserRole, UserSession


class DuplicateEmailRepositoryError(Exception):
    """Raised when attempting to persist a user with an already-registered email."""


class AuthRepository:
    """Database persistence layer for authentication and rate-limiting records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_user_by_email(self, email: str) -> User | None:
        """Find a user by normalized lowercase email."""
        return self._session.scalar(select(User).where(User.email == email))

    def create_user(
        self,
        *,
        email: str,
        full_name: str,
        password_hash: str,
        role: UserRole = UserRole.BUYER,
        is_active: bool = True,
    ) -> User:
        """Insert a new user and flush, translating unique email collisions."""
        user = User(
            email=email,
            full_name=full_name,
            password_hash=password_hash,
            role=role.value,
            is_active=is_active,
        )
        self._session.add(user)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateEmailRepositoryError from exc
        return user

    def update_password_hash(self, user: User, password_hash: str) -> None:
        """Persist an upgraded password hash for an existing user."""
        user.password_hash = password_hash
        self._session.flush()

    def create_session(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        csrf_token: str,
        expires_at: datetime,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> UserSession:
        """Persist a new hashed server-side session bound to a CSRF token."""
        user_session = UserSession(
            user_id=user_id,
            token_hash=token_hash,
            csrf_token=csrf_token,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent[:512] if user_agent else None,
        )
        self._session.add(user_session)
        self._session.flush()
        return user_session

    def get_session_by_token_hash(self, token_hash: str) -> UserSession | None:
        """Fetch a server-side session and eagerly loaded user by token hash."""
        return self._session.scalar(select(UserSession).where(UserSession.token_hash == token_hash))

    def delete_session(self, user_session: UserSession) -> None:
        """Delete a loaded session record."""
        self._session.delete(user_session)
        self._session.flush()

    def delete_session_by_token_hash(self, token_hash: str) -> None:
        """Delete any session matching the given token hash."""
        self._session.execute(delete(UserSession).where(UserSession.token_hash == token_hash))

    def count_recent_attempts(self, scope_key: str, window_start: datetime) -> int:
        """Count failed login attempts for a scope key within the active window."""
        count = self._session.scalar(
            select(func.count(LoginAttempt.id)).where(
                LoginAttempt.scope_key == scope_key,
                LoginAttempt.attempted_at >= window_start,
            )
        )
        return int(count or 0)

    def get_oldest_attempt_in_window(
        self,
        scope_key: str,
        window_start: datetime,
    ) -> datetime | None:
        """Return the earliest failed attempt timestamp within the active window."""
        return self._session.scalar(
            select(func.min(LoginAttempt.attempted_at)).where(
                LoginAttempt.scope_key == scope_key,
                LoginAttempt.attempted_at >= window_start,
            )
        )

    def record_failed_attempt(self, scope_key: str, attempted_at: datetime) -> None:
        """Insert a failed login attempt timestamp for rate limiting."""
        self._session.add(LoginAttempt(scope_key=scope_key, attempted_at=attempted_at))
        self._session.flush()

    def clear_attempts(self, scope_key: str) -> None:
        """Remove all recorded login attempts for a scope key."""
        self._session.execute(delete(LoginAttempt).where(LoginAttempt.scope_key == scope_key))

    def prune_stale_attempts(self, cutoff: datetime) -> None:
        """Delete login attempts older than the active sliding window."""
        self._session.execute(delete(LoginAttempt).where(LoginAttempt.attempted_at < cutoff))

    def commit(self) -> None:
        """Commit the current database transaction."""
        self._session.commit()
