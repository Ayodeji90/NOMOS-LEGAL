"""Add auth_sessions table (SESSION_STORE=postgres)

Revision ID: 005
Revises: 004_add_ng_jurisdiction
Create Date: 2026-09-14

Cloud-neutral session storage for the Azure staging path: a tiny sessions
table with the same logical shape as FirestoreManager's ``sessions``
collection. Firestore remains the default store (SESSION_STORE=firestore);
this table is only used when SESSION_STORE=postgres.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "005_auth_sessions"
down_revision = "004_add_ng_jurisdiction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_session",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_auth_session")),
    )
    op.create_index(
        op.f("ix_auth_session_user_id"), "auth_session", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_auth_session_expires_at"), "auth_session", ["expires_at"], unique=False
    )
    op.create_index(
        "ix_auth_session_user_active", "auth_session", ["user_id", "is_active"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_auth_session_user_active", table_name="auth_session")
    op.drop_index(op.f("ix_auth_session_expires_at"), table_name="auth_session")
    op.drop_index(op.f("ix_auth_session_user_id"), table_name="auth_session")
    op.drop_table("auth_session")
