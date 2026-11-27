"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed runtime settings shared across layers."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "vCraft Bat Trang"
    debug: bool = True
    database_url: str = "postgresql+psycopg://vcraft:vcraft@localhost:5432/vcraft"
    session_cookie_name: str = "vcraft_session"
    session_ttl_seconds: int = 60 * 60 * 24 * 7
    session_cookie_secure: bool = False
    csrf_cookie_name: str = "vcraft_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    csrf_form_field: str = "_csrf_token"
    media_root: str = "storage/media"
    media_max_bytes: int = 10 * 1024 * 1024
    media_max_files_per_request: int = 10
    login_rate_limit_max_attempts: int = 5
    login_rate_limit_window_seconds: int = 60 * 15
