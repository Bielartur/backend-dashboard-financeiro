"""add category_id to merchant_aliases

Revision ID: 798129d08469
Revises: ba270fcb8375
Create Date: 2026-01-26 11:37:00.575615

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "798129d08469"
down_revision: Union[str, Sequence[str], None] = "ba270fcb8375"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "merchant_aliases", sa.Column("category_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        None, "merchant_aliases", "categories", ["category_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint(None, "merchant_aliases", type_="foreignkey")
    op.drop_column("merchant_aliases", "category_id")
