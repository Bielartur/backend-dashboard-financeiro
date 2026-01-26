"""fix_payment_method_enum

Revision ID: 1f62d8b0dfeb
Revises: 8fb7ba9ee198
Create Date: 2026-01-14 16:15:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1f62d8b0dfeb"
down_revision: Union[str, Sequence[str], None] = "8fb7ba9ee198"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Rename existing values to snake_case
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE paymentmethod RENAME VALUE 'Pix' TO 'pix'")
        op.execute(
            "ALTER TYPE paymentmethod RENAME VALUE 'CreditCard' TO 'credit_card'"
        )
        op.execute("ALTER TYPE paymentmethod RENAME VALUE 'DebitCard' TO 'debit_card'")
        op.execute("ALTER TYPE paymentmethod RENAME VALUE 'Other' TO 'other'")

    # 2. Add new values
    # Postgres ALTER TYPE ADD VALUE cannot be run inside a transaction block easily if using 'before/after' clauses,
    # but simple ADD VALUE is fine in newer postgres versions (requires autocommit usually).
    # We use autocommit_block() context to ensure it runs outside a transaction.

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'boleto'")
        op.execute("ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'bill_payment'")
        op.execute(
            "ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'investment_redemption'"
        )


def downgrade() -> None:
    # Downgrading enum value changes is hard in Postgres (requires dropping/recreating type).
    # Since this is a fix, we might not need to support downgrade fully, or we can just reverse renaming.
    # But adding values cannot be easily reversed without recreating type.
    pass
