from sqlalchemy.orm import Session
from contextlib import contextmanager
from functools import wraps
from typing import Callable, Any

@contextmanager
def transaction(db: Session):
    """Context manager for database transactions"""
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        raise e

def transactional(func: Callable) -> Callable:
    """Decorator for transactional operations"""
    @wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        db = kwargs.get('db')
        if not db:
            raise ValueError("db session required")
        
        try:
            result = await func(*args, **kwargs)
            db.commit()
            return result
        except Exception as e:
            db.rollback()
            raise e
    return wrapper