import sys
import os
import asyncio
import json
from datetime import date, datetime
import enum
from sqlalchemy import create_engine, text

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import ONLY the client, avoiding Entity imports that cause SQLAlchemy conflicts
from src.open_finance.client import client

# Import DATABASE_URL loading logic or just use os.getenv
from dotenv import load_dotenv

load_dotenv()


# Helper to serialize dates/decimals
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, enum.Enum):
            return obj.value
        return super().default(obj)


async def dump_all_transactions():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not found in env.")
        return

    try:
        engine = create_engine(database_url)
        connection = engine.connect()
        print("Connected to database.")

        # Raw SQL query to avoid ORM issues
        query = text(
            "SELECT pluggy_account_id, name, type, subtype FROM open_finance_accounts"
        )
        result = connection.execute(query)
        accounts = result.fetchall()

        print(f"Found {len(accounts)} accounts in database.")

        all_data = []

        for acc in accounts:
            # RowProxy access (by index or name depending on sqlalchemy version)
            # Assuming recent sqlalchemy, attribute access works or tuple.
            # print(acc)
            pluggy_id = acc.pluggy_account_id
            name = acc.name
            acc_type = acc.type

            print(f"Fetching transactions for Account: {name} - {pluggy_id}")
            try:
                transactions = await client.get_transactions(pluggy_id)
                print(f"  -> Found {len(transactions)} transactions.")

                # Annotate
                for tx in transactions:
                    tx["_debug_account_name"] = name
                    tx["_debug_account_type"] = str(acc_type)

                all_data.extend(transactions)

            except Exception as e:
                print(f"  -> ERROR fetching transactions: {e}")

        output_file = "full_transactions_dump.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_data, f, indent=2, ensure_ascii=False, cls=DateTimeEncoder)

        print(f"\nSuccessfully dumped {len(all_data)} transactions to {output_file}")

        connection.close()

    except Exception as e:
        print(f"Critical Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(dump_all_transactions())
