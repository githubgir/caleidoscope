"""SQLAlchemy database models for Caleidoscope."""

import uuid
from datetime import datetime

from sqlalchemy import Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class Item(Base):
    """Represents a collected market intelligence item."""

    __tablename__ = "items"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[str | None] = mapped_column(Text, nullable=True)  # ISO 8601
    collected_at: Mapped[str] = mapped_column(Text, nullable=False)  # ISO 8601
    source: Mapped[str] = mapped_column(Text, nullable=False)  # 'msci', 'sp_dji', etc.
    entity: Mapped[str | None] = mapped_column(Text, nullable=True)  # 'MSCI', 'BlackRock', etc.
    category: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # 'index_launch', 'research', etc.
    body: Mapped[str | None] = mapped_column(Text, nullable=True)  # cleaned text
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # LLM-generated
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: '["ESG","ACWI"]'
    raw_html_path: Mapped[str | None] = mapped_column(Text, nullable=True)


class DigestLog(Base):
    """Represents a generated digest."""

    __tablename__ = "digest_log"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    generated_at: Mapped[str] = mapped_column(Text, nullable=False)
    cadence: Mapped[str] = mapped_column(Text, nullable=False)  # 'daily', 'weekly', 'monthly'
    item_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    digest_md: Mapped[str | None] = mapped_column(Text, nullable=True)
