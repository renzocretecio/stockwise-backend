from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.config.settings import settings

engine_options = {
    "echo": settings.ENV == "development",
    "pool_pre_ping": True,
}

if not settings.DATABASE_URL.startswith("sqlite"):
    engine_options.update(
        {
            "pool_size": settings.DATABASE_POOL_SIZE,
            "max_overflow": settings.DATABASE_MAX_OVERFLOW,
            "pool_timeout": settings.DATABASE_POOL_TIMEOUT_SECONDS,
            "pool_recycle": settings.DATABASE_POOL_RECYCLE_SECONDS,
        }
    )

engine = create_engine(settings.DATABASE_URL, **engine_options)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
