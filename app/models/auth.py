from sqlalchemy import Boolean, Column, DateTime, String, Text, func
from sqlalchemy.orm import relationship

from app.models.base import Base, uuid_column


class User(Base):
    __tablename__ = "users"

    id = uuid_column(primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    google_subject = Column(
        String(255),
        unique=True,
        nullable=True,
        index=True,
    )
    password_hash = Column(Text, nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100))
    is_active = Column(Boolean, default=True, nullable=False)
    is_superadmin = Column(Boolean, default=False, nullable=False)
    appearance_palette = Column(
        String(20), default="petrol", server_default="petrol", nullable=False
    )
    appearance_mode = Column(
        String(10), default="system", server_default="system", nullable=False
    )
    appearance_custom_color = Column(String(7), nullable=True)
    last_login_at = Column(DateTime(timezone=True))
    pro_trial_used_at = Column(DateTime(timezone=True))
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    memberships = relationship(
        "BusinessMembership", back_populates="user", cascade="all, delete-orphan"
    )
    audit_logs = relationship("AuditLog", back_populates="user")
