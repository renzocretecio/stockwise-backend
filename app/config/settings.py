from functools import lru_cache

from pydantic import Field
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
    CLAUDE_API_KEY: str
    MODEL_NAME: str = "claude-3-5-haiku-20241022"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    
    # Frontend
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
    }

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()