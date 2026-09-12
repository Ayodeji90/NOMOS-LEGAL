"""Add NG jurisdiction and convert existing data

Revision ID: 004
Revises: 003
Create Date: 2026-09-12 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004_add_ng_jurisdiction'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the enum type for jurisdiction if it doesn't exist
    jurisdiction_enum = postgresql.ENUM('za', 'ng', name='jurisdiction', create_type=False)
    jurisdiction_enum.create(op.get_bind(), checkfirst=True)

    # Convert existing ZA values to lowercase in source table
    op.execute("UPDATE source SET jurisdiction = lower(jurisdiction)")
    # Convert existing ZA values to lowercase in ingestion_run table
    op.execute("UPDATE ingestion_run SET jurisdiction = lower(jurisdiction)")

    # Alter the source.jurisdiction column to use the enum
    op.alter_column('source', 'jurisdiction',
                    existing_type=sa.VARCHAR(length=10),
                    type_=jurisdiction_enum,
                    nullable=False,
                    postgresql_using="jurisdiction::text::jurisdiction")

    # Alter the ingestion_run.jurisdiction column to use the enum
    op.alter_column('ingestion_run', 'jurisdiction',
                    existing_type=sa.VARCHAR(length=10),
                    type_=jurisdiction_enum,
                    nullable=False,
                    postgresql_using="jurisdiction::text::jurisdiction")


def downgrade() -> None:
    # Revert the column types back to VARCHAR
    op.alter_column('ingestion_run', 'jurisdiction',
                    existing_type=postgresql.ENUM('za', 'ng', name='jurisdiction'),
                    type_=sa.VARCHAR(length=10),
                    nullable=False)

    op.alter_column('source', 'jurisdiction',
                    existing_type=postgresql.ENUM('za', 'ng', name='jurisdiction'),
                    type_=sa.VARCHAR(length=10),
                    nullable=False)

    # Drop the enum type
    jurisdiction_enum = postgresql.ENUM('za', 'ng', name='jurisdiction')
    jurisdiction_enum.drop(op.get_bind(), checkfirst=True)