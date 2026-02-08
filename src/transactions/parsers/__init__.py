from .base import BaseParser
from .nubank import NubankParser
from src.transactions.model import ImportSource


def get_parser(source: ImportSource) -> BaseParser:
    if source == ImportSource.NUBANK:
        return NubankParser()
    raise ValueError(f"Nenhum parser encontrado para o banco: {source}")
