"""phylo nodes: point phylogeny edges at nodes instead of species

Revision ID: e0bba7403971
Revises: d691b18aa0e0
Create Date: 2026-10-03 20:07:10

A real phylogeny has internal nodes (unnamed common ancestors) and extinct
groups that are not species, so edges now join `phylo_nodes` rows.
`phylogeny_edges` was never populated under the old species-to-species shape,
so it is recreated rather than altered.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e0bba7403971'
down_revision: Union[str, Sequence[str], None] = 'd691b18aa0e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _require_empty(table: str) -> None:
    count = op.get_bind().execute(sa.text(f"SELECT count(*) FROM {table}")).scalar()
    if count:
        raise RuntimeError(f"{table} has {count} rows; refusing to drop it")


def upgrade() -> None:
    """Upgrade schema."""
    _require_empty("phylogeny_edges")
    op.drop_index(op.f('ix_phylogeny_edges_parent_species_id'), table_name='phylogeny_edges')
    op.drop_index(op.f('ix_phylogeny_edges_child_species_id'), table_name='phylogeny_edges')
    op.drop_table('phylogeny_edges')

    op.create_table('phylo_nodes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=True),
    sa.Column('external_id', sa.String(length=100), nullable=True),
    sa.Column('label', sa.String(length=255), nullable=True),
    sa.Column('is_tip', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('species_id', sa.Integer(), nullable=True),
    sa.Column('family_taxon_id', sa.Integer(), nullable=True),
    sa.Column('family_ott_id', sa.Integer(), nullable=True),
    sa.Column('placement_status', sa.String(length=20), nullable=True),
    sa.Column('extinct', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('collapsed_group', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('placement_uncertain', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('anapsid_skull', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('citation', sa.Text(), nullable=True),
    sa.Column('age_ma', sa.Float(), nullable=True),
    sa.Column('age_ci_low', sa.Float(), nullable=True),
    sa.Column('age_ci_high', sa.Float(), nullable=True),
    sa.Column('age_source', sa.String(length=100), nullable=True),
    sa.Column('age_adjusted', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('first_appearance_ma', sa.Float(), nullable=True),
    sa.Column('last_appearance_ma', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['family_taxon_id'], ['taxa.id'], ),
    sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ),
    sa.ForeignKeyConstraint(['species_id'], ['species.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_phylo_nodes_external_id'), 'phylo_nodes', ['external_id'], unique=False)
    op.create_index(op.f('ix_phylo_nodes_family_taxon_id'), 'phylo_nodes', ['family_taxon_id'], unique=False)
    op.create_index(op.f('ix_phylo_nodes_species_id'), 'phylo_nodes', ['species_id'], unique=False)

    op.create_table('phylogeny_edges',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('parent_node_id', sa.Integer(), nullable=False),
    sa.Column('child_node_id', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=100), nullable=True),
    sa.ForeignKeyConstraint(['child_node_id'], ['phylo_nodes.id'], ),
    sa.ForeignKeyConstraint(['parent_node_id'], ['phylo_nodes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_phylogeny_edges_child_node_id'), 'phylogeny_edges', ['child_node_id'], unique=True)
    op.create_index(op.f('ix_phylogeny_edges_parent_node_id'), 'phylogeny_edges', ['parent_node_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema. Drops all loaded phylogeny data."""
    op.drop_index(op.f('ix_phylogeny_edges_parent_node_id'), table_name='phylogeny_edges')
    op.drop_index(op.f('ix_phylogeny_edges_child_node_id'), table_name='phylogeny_edges')
    op.drop_table('phylogeny_edges')
    op.drop_index(op.f('ix_phylo_nodes_species_id'), table_name='phylo_nodes')
    op.drop_index(op.f('ix_phylo_nodes_family_taxon_id'), table_name='phylo_nodes')
    op.drop_index(op.f('ix_phylo_nodes_external_id'), table_name='phylo_nodes')
    op.drop_table('phylo_nodes')

    op.create_table('phylogeny_edges',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('parent_species_id', sa.Integer(), nullable=True),
    sa.Column('child_species_id', sa.Integer(), nullable=True),
    sa.Column('source', sa.String(length=100), nullable=True),
    sa.ForeignKeyConstraint(['child_species_id'], ['species.id'], ),
    sa.ForeignKeyConstraint(['parent_species_id'], ['species.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_phylogeny_edges_child_species_id'), 'phylogeny_edges', ['child_species_id'], unique=False)
    op.create_index(op.f('ix_phylogeny_edges_parent_species_id'), 'phylogeny_edges', ['parent_species_id'], unique=False)
