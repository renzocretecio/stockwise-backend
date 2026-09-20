from functools import lru_cache

from pydantic import AliasChoices, Field
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = Field("KitaStock API", env="APP_NAME")
    API_V1_STR: str = Field("/api/v1", env="API_PREFIX")

    # Server
    PORT: int = 3001
    HOST: str = "0.0.0.0"
    ENV: str = "development"

    # Database
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = Field(default=3, ge=1, le=10)
    DATABASE_MAX_OVERFLOW: int = Field(default=2, ge=0, le=10)
    DATABASE_POOL_TIMEOUT_SECONDS: int = Field(default=30, ge=1)
    DATABASE_POOL_RECYCLE_SECONDS: int = Field(default=1800, ge=1)

    # JWT
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7

    # Google OpenID Connect. KitaStock uses Google only for authentication,
    # so provider access and refresh tokens are never persisted.
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: Optional[str] = None
    GOOGLE_OAUTH_TIMEOUT_SECONDS: float = 10.0

    # LLM
    NARRATOR_PROVIDER: str = "template"
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    NARRATOR_TIMEOUT_SECONDS: float = 60.0

    # Platform administration. The email list is a bootstrap fallback; use the
    # database-backed superadmin flag for ongoing access management.
    BILLING_ADMIN_TOKEN: Optional[str] = None
    BILLING_ADMIN_EMAILS: str = ""

    # Email delivery
    APP_URL: str = "http://localhost:3000"
    BREVO_API_KEY: Optional[str] = None
    BREVO_SENDER_EMAIL: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "BREVO_SENDER_EMAIL",
            "BREVO_FROM_EMAIL",
            "EMAIL_FROM",
        ),
    )
    BREVO_SENDER_NAME: str = "KitaStock"
    BREVO_API_URL: str = "https://api.brevo.com/v3/smtp/email"
    BREVO_API_TIMEOUT_SECONDS: float = 15.0

    # Scheduled jobs
    CRON_SECRET: Optional[str] = None
    LOG_LEVEL: str = "INFO"

    # Frontend
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
