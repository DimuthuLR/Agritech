"""
ChatSession — persistent conversation history.

Replaces the stateless chat flow (client sends the last 10 turns on
every request) with server-side session storage. Enables:

  - Resume after page reload
  - List past conversations for a user
  - Analytics on what farmers actually ask
  - Tenant admin review of assistant answers

Messages are stored as JSONB — a list of {role, content, created_at}.
Upgrade path: if you ever need to query individual messages (search,
sentiment, per-message ratings), migrate to a separate chat_messages
table. Not needed at pilot scale.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    String, Integer, Boolean, DateTime, ForeignKey, Index, func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional plot scope. When set, the assistant has full context
    # for that plot (sensors, weather, recent decisions, overrides).
    plot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plots.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Auto-derived from the first user message. User can rename later.
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Conversation: [{role, content, created_at}, ...]
    # Capped in code (Phase 10.6) at a configurable max (~50 turns).
    messages: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    __table_args__ = (
        # Fast "list recent sessions for this tenant" queries
        Index("ix_chat_sessions_tenant_last_msg", "tenant_id", "last_message_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ChatSession {self.id} tenant={self.tenant_id} "
            f"msgs={self.message_count}>"
        )