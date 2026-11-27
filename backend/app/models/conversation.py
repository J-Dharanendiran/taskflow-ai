
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.types import UTCDateTime


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(UTC)


class Conversation(Base):
    """A persistent user conversation associated with a LangGraph thread."""

    __tablename__ = "conversations"

    thread_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    title: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
    )


class Message(Base):
    """A user-visible message belonging to a conversation."""

    __tablename__ = "messages"

    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_messages_valid_role",
        ),
        Index(
            "ix_messages_conversation_created_id",
            "conversation_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversations.thread_id"),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )

    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages",
    )
