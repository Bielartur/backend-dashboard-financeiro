"""move_type_from_category_to_payment

Revision ID: c2ef90973c9b
Revises: 95a97440f1e6
Create Date: 2026-01-23 13:13:21.273527

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c2ef90973c9b"
down_revision: Union[str, Sequence[str], None] = "95a97440f1e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create the new enum type
    transaction_type = sa.Enum("income", "expense", name="transactiontype")
    transaction_type.create(op.get_bind(), checkfirst=True)

    # Add column as nullable first
    op.add_column(
        "payments",
        sa.Column(
            "type", sa.Enum("income", "expense", name="transactiontype"), nullable=True
        ),
    )

    # Data migration: Set Type based on Amount
    op.execute("UPDATE payments SET type = 'expense' WHERE amount < 0")
    op.execute("UPDATE payments SET type = 'income' WHERE amount >= 0")

    # Handle any nulls (safeguard, though above covers all numbers)
    op.execute("UPDATE payments SET type = 'expense' WHERE type IS NULL")

    # Alter to non-nullable
    op.alter_column("payments", "type", nullable=False)

    # Drop old column
    op.drop_column("categories", "type")

    # Drop old enum type if desired, or leave it
    op.execute("DROP TYPE IF EXISTS categorytype")


def downgrade() -> None:
    """Downgrade schema."""
    # This downgrade is approximate/lossy because we lost the original Category Types

    # Re-create old enum
    category_type = sa.Enum("income", "expense", "neutral", name="categorytype")
    category_type.create(op.get_bind(), checkfirst=True)

    # Add column back
    op.add_column(
        "categories",
        sa.Column(
            "type",
            postgresql.ENUM("income", "expense", "neutral", name="categorytype"),
            autoincrement=False,
            nullable=True,
        ),
    )

    # Attempt to restore type based on... impossible to know for sure, default to expense
    op.execute("UPDATE categories SET type = 'expense'")
    op.alter_column("categories", "type", nullable=False)

    op.drop_column("payments", "type")
    op.execute("DROP TYPE IF EXISTS transactiontype")
