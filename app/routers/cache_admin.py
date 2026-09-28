"""Endpoints de administração do cache (Parte 3).

Complementam a invalidação automática: servem para limpar o cache sob
demanda (administração, demonstração e testes de desempenho, que precisam
partir de um cache vazio) e para acompanhar o estado do Redis.
"""
from fastapi import APIRouter

from app import cache
from app.database import SessionDep
from app import repository
from app.schemas import CacheInvalidationOut, CacheStatsOut

router = APIRouter(prefix="/cache", tags=["Cache"])


@router.get("/stats", response_model=CacheStatsOut,
            summary="Estado atual do cache de recomendações")
def cache_stats():
    return cache.stats()


@router.delete("/users/{user_name}", response_model=CacheInvalidationOut,
               summary="Invalidar o cache de um usuário",
               responses={404: {"description": "Usuário não encontrado."}})
def invalidate_user_cache(user_name: str, session: SessionDep):
    """Apaga as recomendações em cache de um usuário.

    O usuário é verificado no Neo4j antes, para que um nome digitado errado
    devolva 404 em vez de um silencioso "0 chaves removidas".
    """
    session.execute_read(repository.get_user, user_name)
    removed = cache.invalidate_user(user_name)
    return {"user": user_name, "keys_removed": removed}


@router.delete("", response_model=CacheInvalidationOut,
               summary="Invalidar todo o cache de recomendações")
def invalidate_all_cache():
    """Apaga todas as recomendações em cache (apenas as chaves `rec:*`)."""
    return {"user": None, "keys_removed": cache.invalidate_all()}
