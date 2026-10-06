"""phylo node age provenance: citation, study count, pre-adjustment estimate

Revision ID: b4dcc12d4cee
Revises: e0bba7403971
Create Date: 2026-10-03 21:37:14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4dcc12d4cee'
down_revision: Union[str, Sequence[str], None] = 'e0bba7403971'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('phylo_nodes', sa.Column('age_citation', sa.Text(), nullable=True))
    op.add_column('phylo_nodes', sa.Column('age_study_count', sa.Integer(), nullable=True))
    op.add_column('phylo_nodes', sa.Column('age_unadjusted_ma', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('phylo_nodes', 'age_unadjusted_ma')
    op.drop_column('phylo_nodes', 'age_study_count')
    op.drop_column('phylo_nodes', 'age_citation')
