from abc import ABC, abstractmethod
from typing import List
from fastapi import UploadFile
from src.payments.model import PaymentImportResponse


class BaseParser(ABC):
    @abstractmethod
    async def parse(self, file: UploadFile) -> List[PaymentImportResponse]:
        """
        Parses a file and returns a list of PaymentImportResponse objects.
        """
        pass
