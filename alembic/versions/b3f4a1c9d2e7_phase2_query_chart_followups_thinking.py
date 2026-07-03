"""phase2 query chart_spec/followups/thinking_tokens columns

Revision ID: b3f4a1c9d2e7
Revises: 825aebc0ca14
Create Date: 2026-07-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f4a1c9d2e7'
down_revision: Union[str, None] = '825aebc0ca14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('queries', sa.Column('chart_spec_json', sa.Text(), nullable=True))
    op.add_column('queries', sa.Column('suggested_followups_json', sa.Text(), nullable=True))
    op.add_column('queries', sa.Column('thinking_tokens', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('queries', 'thinking_tokens')
    op.drop_column('queries', 'suggested_followups_json')
    op.drop_column('queries', 'chart_spec_json')
