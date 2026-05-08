import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    github_url: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    stars: Mapped[int] = mapped_column(Integer, default=0)
    default_branch: Mapped[str | None] = mapped_column(String(100))
    primary_language: Mapped[str | None] = mapped_column(String(100))
    # PENDING → CLONING → PROCESSING → COMPLETED | FAILED
    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    processed_files: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    files: Mapped[list["CodeFile"]] = relationship(
        "CodeFile", back_populates="repository", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["ChatSession"]] = relationship(
        "ChatSession", back_populates="repository", cascade="all, delete-orphan"
    )
