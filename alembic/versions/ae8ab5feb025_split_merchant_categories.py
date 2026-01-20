"""split_merchant_categories

Revision ID: ae8ab5feb025
Revises: 1f62d8b0dfeb
Create Date: 2026-01-16 12:35:02.574129

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ae8ab5feb025"
down_revision: Union[str, Sequence[str], None] = "1f62d8b0dfeb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "merchants", sa.Column("income_category_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "merchants", sa.Column("expense_category_id", sa.UUID(), nullable=True)
    )

    op.create_foreign_key(
        "fk_merchants_income_category",
        "merchants",
        "categories",
        ["income_category_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_merchants_expense_category",
        "merchants",
        "categories",
        ["expense_category_id"],
        ["id"],
    )

    # Data Migration
    op.execute(
        """
        UPDATE merchants
        SET income_category_id = category_id
        FROM categories
        WHERE merchants.category_id = categories.id AND categories.type = 'income'
    """
    )
    op.execute(
        """
        UPDATE merchants
        SET expense_category_id = category_id
        FROM categories
        WHERE merchants.category_id = categories.id AND categories.type = 'expense'
    """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_merchants_expense_category", "merchants", type_="foreignkey")
    op.drop_constraint("fk_merchants_income_category", "merchants", type_="foreignkey")
    op.drop_column("merchants", "expense_category_id")
    op.drop_column("merchants", "income_category_id")
