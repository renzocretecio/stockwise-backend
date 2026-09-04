from functools import lru_cache

from pydantic import AliasChoices, Field
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = Field("stockwise API", env="APP_NAME")
    API_V1_STR: str = Field("/api/v1", env="API_PREFIX")

    # Server
    PORT: int = 3001
    HOST: str = "0.0.0.0"
    ENV: str = "development"
    
    # Database
    DATABASE_URL: str
    
    # JWT
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7
    
    # LLM
    NARRATOR_PROVIDER: str = "template"
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    NARRATOR_TIMEOUT_SECONDS: float = 60.0

    # Weekly owner email
    APP_URL: str = "http://localhost:3000"
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("SMTP_FROM_EMAIL", "SMTP_FROM"),
    )
    SMTP_USE_TLS: bool = True
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    
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
