"""normalize_enum_casing

Revision ID: 8fb7ba9ee198
Revises: 04c54eba65d8
Create Date: 2026-01-13 13:15:44.303473

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8fb7ba9ee198"
down_revision: Union[str, Sequence[str], None] = "04c54eba65d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE categorytype RENAME VALUE 'INCOME' TO 'income'")
    op.execute("ALTER TYPE categorytype RENAME VALUE 'EXPENSE' TO 'expense'")


def downgrade() -> None:
    """Downgrade schema."""
    pass
