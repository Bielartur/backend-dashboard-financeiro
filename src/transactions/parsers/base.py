from abc import ABC, abstractmethod
from typing import List
from fastapi import UploadFile
from src.transactions.model import TransactionImportResponse
import csv
import io


class BaseParser(ABC):
    @abstractmethod
    async def parse_invoice(self, file: UploadFile) -> List[TransactionImportResponse]:
        """
        Parses a credit card invoice file and returns a list of TransactionImportResponse objects.
        """
        pass

    @abstractmethod
    async def parse_statement(
        self, file: UploadFile
    ) -> List[TransactionImportResponse]:
        """
        Parses a bank statement file and returns a list of TransactionImportResponse objects.
        """
        pass

    async def _read_csv(self, file: UploadFile) -> List[TransactionImportResponse]:
        content = await file.read()
        decoded_content = content.decode("utf-8")
        csv_reader = csv.DictReader(io.StringIO(decoded_content))

        return csv_reader
