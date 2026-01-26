# Add the project root to sys.path
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.getcwd(), ".")))

from src.database.core import SessionLocal
from src.dashboard.service import get_dashboard_data
from src.entities.user import User
from src.entities.category import Category
from src.entities.merchant import Merchant
from src.entities.bank import Bank
from src.entities.merchant_alias import MerchantAlias
from src.entities.payment import TransactionType


def verify_dashboard():
    db = SessionLocal()
    try:
        # Get a user (assuming there is at least one)
        user = db.query(User).first()
        if not user:
            print("No user found to test.")
            return

        print(f"Testing dashboard for user: {user.email} ({user.id})")

        # Call the service
        dashboard = get_dashboard_data(db, user.id, "last-12")

        print(f"Global Balance: {dashboard.summary.balance}")
        print(f"Global Revenue: {dashboard.summary.total_revenue}")
        print(f"Global Expenses: {dashboard.summary.total_expenses}")

        print("\nMonthly Data (First 3 months):")
        for month in dashboard.months[:3]:
            print(
                f"  {month.month}/{month.year}: Revenue={month.revenue}, Expenses={month.expenses}, Balance={month.balance}"
            )
            if month.categories:
                print("    Top level categories:")
                for cat in month.categories:
                    print(
                        f"      - {cat.name} ({cat.type}): {cat.total} (Status: {cat.status})"
                    )

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    verify_dashboard()
