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
