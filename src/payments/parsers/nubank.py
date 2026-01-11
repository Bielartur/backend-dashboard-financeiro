from typing import List
from fastapi import UploadFile
from .base import BaseParser
from src.payments.model import PaymentImportResponse
from datetime import datetime
from decimal import Decimal
import csv
import io
import re


class NubankParser(BaseParser):
    async def parse(self, file: UploadFile) -> List[PaymentImportResponse]:
        content = await file.read()
        decoded_content = content.decode("utf-8")
        csv_reader = csv.DictReader(io.StringIO(decoded_content))

        transactions = []
        for row in csv_reader:
            # Nubank CSV format usually has: date, category, title, amount
            # We map: date -> date, title -> title, amount -> amount

            # Parse date (assuming format YYYY-MM-DD or similar, adjustment might be needed based on actual CSV)
            # Standard Nubank CSV usually has YYYY-MM-DD
            try:
                date_str = row.get("date")
                amount_str = row.get("amount")
                title = row.get("title")

                if not date_str or not amount_str or not title:
                    continue

                payment_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                amount = Decimal(amount_str)

                # Cleaning title to remove installment info (e.g. " - Parcela 1/12")
                # Regex looks for " - Parcela X/Y" and replaces with empty string
                clean_title = re.sub(
                    r"\s*-\s*Parcela\s+\d+/\d+", "", title, flags=re.IGNORECASE
                )

                transactions.append(
                    PaymentImportResponse(
                        date=payment_date,
                        title=clean_title.strip(),  # Ensure no trailing whitespace
                        amount=amount,
                        category=None,  # Category will be filled by service
                    )
                )
            except Exception as e:
                # Log error or skip line
                continue

        return transactions
