"""add mechanic_embedding column

Revision ID: c0af39cade6a
Revises: 696749d275f6
Create Date: 2026-03-02 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import pgvector.sqlalchemy.vector
import sqlalchemy as sa
from dejaship.config import settings

revision: str = 'c0af39cade6a'
down_revision: Union[str, Sequence[str], None] = '696749d275f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agent_intents',
        sa.Column('mechanic_embedding',
            pgvector.sqlalchemy.vector.VECTOR(dim=settings.VECTOR_DIMENSIONS),
            nullable=True)
    )


def downgrade() -> None:
    op.drop_column('agent_intents', 'mechanic_embedding')
