"""species media: images with credits, Wikipedia link, IUCN status source

Revision ID: ee20df877b61
Revises: b4dcc12d4cee
Create Date: 2026-10-06 13:31:39

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ee20df877b61'
down_revision: Union[str, Sequence[str], None] = 'b4dcc12d4cee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('species', sa.Column('iucn_source', sa.Text(), nullable=True))
    op.add_column('species', sa.Column('wikipedia_url', sa.Text(), nullable=True))
    op.create_table('species_media',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('species_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=50), nullable=False),
    sa.Column('image_url', sa.Text(), nullable=False),
    sa.Column('thumbnail_url', sa.Text(), nullable=True),
    sa.Column('page_url', sa.Text(), nullable=True),
    sa.Column('licence', sa.String(length=50), nullable=False),
    sa.Column('licence_url', sa.Text(), nullable=True),
    sa.Column('creator', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['species_id'], ['species.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_species_media_species_id'), 'species_media', ['species_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_species_media_species_id'), table_name='species_media')
    op.drop_table('species_media')
    op.drop_column('species', 'wikipedia_url')
    op.drop_column('species', 'iucn_source')
