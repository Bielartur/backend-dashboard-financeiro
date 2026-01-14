from abc import ABC, abstractmethod
from typing import List
from fastapi import UploadFile
from src.payments.model import PaymentImportResponse


class BaseParser(ABC):
    @abstractmethod
    async def parse_invoice(self, file: UploadFile) -> List[PaymentImportResponse]:
        """
        Parses a credit card invoice file and returns a list of PaymentImportResponse objects.
        """
        pass

    @abstractmethod
    async def parse_statement(self, file: UploadFile) -> List[PaymentImportResponse]:
        """
        Parses a bank statement file and returns a list of PaymentImportResponse objects.
        """
        pass

    async def _read_csv(self, file: UploadFile) -> List[PaymentImportResponse]:
        content = await file.read()
        decoded_content = content.decode("utf-8")
        csv_reader = csv.DictReader(io.StringIO(decoded_content))

        return csv_reader
