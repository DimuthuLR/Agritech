"""add knowledge_documents table

Revision ID: b0609b8f9ec1
Revises: d6c7e313333a
Create Date: 2026-10-07 22:21:48.957067

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = 'b0609b8f9ec1'
down_revision: Union[str, None] = 'd6c7e313333a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


EMBEDDING_DIM = 1024


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source", sa.String(512), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("language", sa.String(8), nullable=False, server_default="en"),
        sa.Column("crop", sa.String(64), nullable=True),
        sa.Column("topic", sa.String(64), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("metadata", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_knowledge_documents_source",
        "knowledge_documents",
        ["source"],
    )
    op.create_index(
        "ix_knowledge_documents_source_hash",
        "knowledge_documents",
        ["source_hash"],
    )
    op.create_index(
        "ix_knowledge_documents_crop",
        "knowledge_documents",
        ["crop"],
    )
    op.create_index(
        "ix_knowledge_documents_topic",
        "knowledge_documents",
        ["topic"],
    )
    op.create_index(
        "ix_knowledge_documents_source_chunk",
        "knowledge_documents",
        ["source", "chunk_index"],
    )

    # HNSW index for fast cosine-similarity search.
    op.execute(
        "CREATE INDEX ix_knowledge_documents_embedding_hnsw "
        "ON knowledge_documents "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_documents_embedding_hnsw")
    op.drop_index("ix_knowledge_documents_source_chunk", "knowledge_documents")
    op.drop_index("ix_knowledge_documents_topic", "knowledge_documents")
    op.drop_index("ix_knowledge_documents_crop", "knowledge_documents")
    op.drop_index("ix_knowledge_documents_source_hash", "knowledge_documents")
    op.drop_index("ix_knowledge_documents_source", "knowledge_documents")
    op.drop_table("knowledge_documents")