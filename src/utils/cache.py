"""
Módulo centralizado para gerenciamento de cache da aplicação.
"""
from cachetools import TTLCache
import logging

logger = logging.getLogger(__name__)

# Cache para descendentes de categorias
# maxsize=1000: até 1000 categorias diferentes podem ser cacheadas
# ttl=3600: cada entrada expira após 1 hora (3600 segundos)
category_descendants_cache: TTLCache = TTLCache(maxsize=1000, ttl=3600)


def invalidate_category_cache() -> None:
    """
    Invalida o cache de hierarquia de categorias.
    Deve ser chamado quando categorias são criadas, modificadas ou deletadas.
    """
    category_descendants_cache.clear()
    logger.info("Cache de hierarquia de categorias invalidado")


def get_cache_stats() -> dict:
    """
    Retorna estatísticas sobre o cache de categorias.
    Útil para monitoramento e debugging.
    """
    return {
        "category_descendants_cache": {
            "current_size": len(category_descendants_cache),
            "max_size": category_descendants_cache.maxsize,
            "ttl_seconds": category_descendants_cache.ttl,
            "items": list(category_descendants_cache.keys())[:10]  # Primeiros 10 para preview
        }
    }
