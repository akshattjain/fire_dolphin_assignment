import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class CodeFile(Base):
    __tablename__ = "code_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    repo_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    language: Mapped[str | None] = mapped_column(String(50))
    s3_key: Mapped[str | None] = mapped_column(String(1000))
    file_size: Mapped[int] = mapped_column(Integer, default=0)

    repository: Mapped["Repository"] = relationship("Repository", back_populates="files")
    chunks: Mapped[list["CodeChunk"]] = relationship(
        "CodeChunk", back_populates="file", cascade="all, delete-orphan"
    )


class CodeChunk(Base):
    __tablename__ = "code_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("code_files.id", ondelete="CASCADE"), nullable=False
    )
    chunk_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str | None] = mapped_column(String(500))
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(36))

    file: Mapped["CodeFile"] = relationship("CodeFile", back_populates="chunks")
