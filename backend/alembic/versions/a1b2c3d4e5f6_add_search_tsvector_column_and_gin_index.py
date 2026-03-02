"""add search_tsvector column and gin index

Revision ID: a1b2c3d4e5f6
Revises: c0af39cade6a
Create Date: 2026-03-02 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'c0af39cade6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add tsvector column
    op.add_column('agent_intents',
        sa.Column('search_tsvector', TSVECTOR(), nullable=True)
    )
    # GIN index for efficient FTS
    op.create_index(
        'ix_agent_intents_search_tsvector',
        'agent_intents',
        ['search_tsvector'],
        postgresql_using='gin'
    )
    # Populate existing rows (for rows already in the DB before this migration)
    op.execute("""
        UPDATE agent_intents
        SET search_tsvector = to_tsvector('english',
            core_mechanic || ' ' || array_to_string(keywords, ' '))
    """)


def downgrade() -> None:
    op.drop_index('ix_agent_intents_search_tsvector', table_name='agent_intents')
    op.drop_column('agent_intents', 'search_tsvector')
