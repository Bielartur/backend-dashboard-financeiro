from typing import List
from uuid import UUID
from fastapi import UploadFile
from .base import BaseParser
from src.payments.model import PaymentImportResponse
from datetime import datetime
from decimal import Decimal
import re


from src.entities.payment import PaymentMethod


class NubankParser(BaseParser):
    async def parse_invoice(self, file: UploadFile) -> List[PaymentImportResponse]:
        csv_reader = await self._read_csv(file)

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

                # Invoices list purchases as positive. We negate them to represent expenses.
                # Credits/payments are negative in CSV, so negating them makes them positive (income).
                amount = -Decimal(amount_str)

                # Cleaning title to remove installment info (e.g. " - Parcela 1/12")
                # Regex looks for " - Parcela X/Y" and replaces with empty string
                clean_title = re.sub(
                    r"\s*-\s*Parcela\s+\d+/\d+", "", title, flags=re.IGNORECASE
                )
                if clean_title == "Pagamento recebido":
                    payment_method = PaymentMethod.BillPayment
                else:
                    payment_method = PaymentMethod.CreditCard

                transactions.append(
                    PaymentImportResponse(
                        date=payment_date,
                        title=clean_title.strip(),  # Ensure no trailing whitespace
                        amount=amount,
                        category=None,  # Category will be filled by service
                        payment_method=payment_method,
                    )
                )
            except Exception as e:
                # Log error or skip line
                continue

        return transactions

    async def parse_statement(self, file: UploadFile) -> List[PaymentImportResponse]:
        csv_reader = await self._read_csv(file)
        transactions = []

        for row in csv_reader:
            try:
                # Nubank statement columns: data, valor, identificador, descrição
                date_str = row.get("Data") or row.get("data")
                amount_str = row.get("Valor") or row.get("valor")
                identificador = row.get("Identificador") or row.get("identificador")
                description = row.get("Descrição") or row.get("descrição")

                if not date_str or not amount_str or not description:
                    continue

                payment_date = datetime.strptime(date_str, "%d/%m/%Y").date()
                amount = Decimal(amount_str)

                # Check for "identificador" being a UUID
                payment_id = None
                if identificador:
                    try:
                        payment_id = UUID(identificador)
                    except ValueError:
                        pass  # Keep None if not a valid UUID

                payment_method = PaymentMethod.Other

                # Regex mapping
                if re.search(
                    r"Transfer.ncia (enviada|recebida)( pelo Pix)?",
                    description,
                    re.IGNORECASE,
                ):
                    payment_method = PaymentMethod.Pix
                elif (
                    re.search(r"Compra no d.bito", description, re.IGNORECASE)
                    or re.search(r"Compra de criptomoedas", description, re.IGNORECASE)
                    or re.search(r"Venda de criptomoedas", description, re.IGNORECASE)
                    or re.search(r"D.bito em conta", description, re.IGNORECASE)
                    or re.search(r"Recarga de celular", description, re.IGNORECASE)
                ):
                    payment_method = PaymentMethod.DebitCard
                elif re.search(r"Pagamento de boleto", description, re.IGNORECASE):
                    payment_method = PaymentMethod.Boleto
                elif re.search(r"Pagamento de fatura", description, re.IGNORECASE):
                    payment_method = PaymentMethod.BillPayment
                elif re.search(r"Resgate RDB", description, re.IGNORECASE):
                    payment_method = PaymentMethod.InvestmentRedemption

                # Fallback for "Transferência Recebida" without "pelo Pix" is already covered by the first regex

                final_title = description.strip()
                if " - " in final_title:
                    parts = final_title.split(" - ")
                    if len(parts) > 1:
                        final_title = parts[1].strip()

                transactions.append(
                    PaymentImportResponse(
                        id=payment_id,
                        date=payment_date,
                        title=final_title,
                        amount=amount,
                        category=None,
                        payment_method=payment_method,
                    )
                )

            except Exception as e:
                # Log error or skip line
                print(f"Error parsing line: {row} - {e}")
                continue

        return transactions
