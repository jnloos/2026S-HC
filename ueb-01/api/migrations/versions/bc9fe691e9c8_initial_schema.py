"""initial schema

Revision ID: bc9fe691e9c8
Revises:
Create Date: 2026-05-27 14:05:53.573809

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'bc9fe691e9c8'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pools',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('pools', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pools_name'), ['name'], unique=True)

    op.create_table(
        'contents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pool_id', sa.Integer(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(['pool_id'], ['pools.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('contents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_contents_pool_id'), ['pool_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('contents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_contents_pool_id'))
    op.drop_table('contents')

    with op.batch_alter_table('pools', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pools_name'))
    op.drop_table('pools')
