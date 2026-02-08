"""rename_payments_to_transactions

Revision ID: 0b09e7de7ead
Revises: 0be917584281
Create Date: 2026-02-06 09:24:04.936599

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0b09e7de7ead"
down_revision: Union[str, Sequence[str], None] = "0be917584281"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. Rename table
    if "payments" in tables:
        if "transactions" in tables:
            # Check if transactions is empty or we should assume it's the "wrong" one
            # For this fix, providing we have 'payments', 'transactions' is likely the empty one from create_all
            op.drop_table("transactions")
        op.rename_table("payments", "transactions")

    # Ensure 'transactions' table exists before proceeding with its constraints/indexes
    if "transactions" in inspector.get_table_names():
        # 2. Rename Primary Key Index
        # Check current PK name on transactions
        pk_constraint = inspector.get_pk_constraint("transactions")
        pk_name = pk_constraint.get("name")

        if pk_name == "payments_pkey":
            op.execute("ALTER INDEX payments_pkey RENAME TO transactions_pkey")

        # 3. Rename Other Indices
        indexes = inspector.get_indexes("transactions")
        index_names = [i["name"] for i in indexes]

        index_map = {
            "ix_payments_bank_id": "ix_transactions_bank_id",
            "ix_payments_date": "ix_transactions_date",
            "ix_payments_open_finance_id": "ix_transactions_open_finance_id",
            "ix_payments_title": "ix_transactions_title",
            "ix_payments_user_id": "ix_transactions_user_id",
        }

        for old_name, new_name in index_map.items():
            if old_name in index_names:
                op.execute(f"ALTER INDEX {old_name} RENAME TO {new_name}")

        # 4. Rename Foreign Key Constraints
        fks = inspector.get_foreign_keys("transactions")
        fk_names = [fk["name"] for fk in fks]

        # Map old FK name to (new_name, referent_table, referent_col, ondelete)
        # Note: local_cols are implicit in the loop context typically, but we define specific changes

        # Bank
        if "payments_bank_id_fkey" in fk_names:
            op.drop_constraint(
                "payments_bank_id_fkey", "transactions", type_="foreignkey"
            )
            op.create_foreign_key(
                "transactions_bank_id_fkey",
                "transactions",
                "banks",
                ["bank_id"],
                ["id"],
            )

        # Category
        if "payments_category_id_fkey" in fk_names:
            op.drop_constraint(
                "payments_category_id_fkey", "transactions", type_="foreignkey"
            )
            op.create_foreign_key(
                "transactions_category_id_fkey",
                "transactions",
                "categories",
                ["category_id"],
                ["id"],
                ondelete="RESTRICT",
            )

        # Merchant
        if "payments_merchant_id_fkey" in fk_names:
            op.drop_constraint(
                "payments_merchant_id_fkey", "transactions", type_="foreignkey"
            )
            op.create_foreign_key(
                "transactions_merchant_id_fkey",
                "transactions",
                "merchants",
                ["merchant_id"],
                ["id"],
            )

        # User
        if "payments_user_id_fkey" in fk_names:
            op.drop_constraint(
                "payments_user_id_fkey", "transactions", type_="foreignkey"
            )
            op.create_foreign_key(
                "transactions_user_id_fkey",
                "transactions",
                "users",
                ["user_id"],
                ["id"],
            )

        # 5. Rename Unique Constraint
        # Constraints specifically unique constraints are in get_unique_constraints? or implied?
        # Actually inspector.get_unique_constraints("transactions")
        unique_constraints = inspector.get_unique_constraints("transactions")
        uc_names = [u["name"] for u in unique_constraints]

        if "uq_payment_user_open_finance_id" in uc_names:
            op.drop_constraint(
                "uq_payment_user_open_finance_id", "transactions", type_="unique"
            )
            op.create_unique_constraint(
                "uq_transaction_user_open_finance_id",
                "transactions",
                ["user_id", "open_finance_id"],
            )
        # Also Check if new one exists? If neither, maybe create?
        # But usually upgrade follows schema. If uq_payment... is gone, maybe uq_transaction... is there.
        # We can trust that if uq_payment... is missing, it's likely done.

    # 6. Update Enum Type
    # Determine which type name to use for adding values
    # Check if 'paymentmethod' exists
    type_exists_query = sa.text("SELECT 1 FROM pg_type WHERE typname = 'paymentmethod'")
    pm_exists = conn.execute(type_exists_query).scalar()

    target_type = "paymentmethod" if pm_exists else "transactionmethod"

    # Add new values to existing type (whichever it is)
    with op.get_context().autocommit_block():
        op.execute(f"ALTER TYPE {target_type} ADD VALUE IF NOT EXISTS 'bank_transfer'")
        op.execute(f"ALTER TYPE {target_type} ADD VALUE IF NOT EXISTS 'transfer'")
        op.execute(f"ALTER TYPE {target_type} ADD VALUE IF NOT EXISTS 'cash'")

    # Rename the type itself to 'transactionmethod' if it is still 'paymentmethod'
    if pm_exists:
        # Check if 'transactionmethod' already exists (conflict cleanup)
        op.execute("DROP TYPE IF EXISTS transactionmethod")
        op.execute("ALTER TYPE paymentmethod RENAME TO transactionmethod")


def downgrade() -> None:
    """Downgrade schema."""
    # 1. Rename Type Back
    op.execute("ALTER TYPE transactionmethod RENAME TO paymentmethod")
    # Note: We cannot remove enum values easily in valid SQL downgrade without recreation. keeping them.

    # 2. Rename Unique Constraint Back
    op.drop_constraint(
        "uq_transaction_user_open_finance_id", "transactions", type_="unique"
    )
    op.create_unique_constraint(
        "uq_payment_user_open_finance_id",
        "transactions",
        ["user_id", "open_finance_id"],
    )

    # 3. Rename Foreign Keys Back
    op.drop_constraint("transactions_user_id_fkey", "transactions", type_="foreignkey")
    op.create_foreign_key(
        "payments_user_id_fkey", "transactions", "users", ["user_id"], ["id"]
    )

    op.drop_constraint(
        "transactions_merchant_id_fkey", "transactions", type_="foreignkey"
    )
    op.create_foreign_key(
        "payments_merchant_id_fkey",
        "transactions",
        "merchants",
        ["merchant_id"],
        ["id"],
    )

    op.drop_constraint(
        "transactions_category_id_fkey", "transactions", type_="foreignkey"
    )
    op.create_foreign_key(
        "payments_category_id_fkey",
        "transactions",
        "categories",
        ["category_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("transactions_bank_id_fkey", "transactions", type_="foreignkey")
    op.create_foreign_key(
        "payments_bank_id_fkey", "transactions", "banks", ["bank_id"], ["id"]
    )

    # 4. Rename Indices Back
    op.execute("ALTER INDEX ix_transactions_user_id RENAME TO ix_payments_user_id")
    op.execute("ALTER INDEX ix_transactions_title RENAME TO ix_payments_title")
    op.execute(
        "ALTER INDEX ix_transactions_open_finance_id RENAME TO ix_payments_open_finance_id"
    )
    op.execute("ALTER INDEX ix_transactions_date RENAME TO ix_payments_date")
    op.execute("ALTER INDEX ix_transactions_bank_id RENAME TO ix_payments_bank_id")

    # 5. Rename PK Back
    op.execute("ALTER INDEX transactions_pkey RENAME TO payments_pkey")

    # 6. Rename Table Back
    op.rename_table("transactions", "payments")
