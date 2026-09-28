"""Endpoint de recomendações personalizadas, com cache em Redis (Parte 3)."""
import time

from fastapi import APIRouter, Query

from app import cache, repository
from app.database import SessionDep
from app.schemas import RecommendationResponse

router = APIRouter(tags=["Recomendações"])


@router.get(
    "/users/{user_name}/recommendations",
    response_model=RecommendationResponse,
    summary="Gerar recomendações personalizadas para um usuário",
    responses={404: {"description": "Usuário não encontrado."}},
)
def get_recommendations(
    user_name: str,
    session: SessionDep,
    limit: int = Query(10, ge=1, le=50, description="Máximo de filmes retornados."),
):
    """Executa a consulta `neo4j/recomendacao.cypher` para o usuário informado.

    Estratégia de cache (padrão cache-aside):

    1. procura a recomendação no Redis;
    2. se encontrar, devolve na hora e marca CACHE HIT (o Neo4j não é consultado);
    3. se não encontrar, consulta o Neo4j, grava o resultado no Redis com TTL
       e marca CACHE MISS.

    O nome recebido na URL é passado ao parâmetro `$userName` da consulta;
    nenhuma parte da lógica é específica de um usuário.
    """
    started = time.perf_counter()
    key = cache.build_key(user_name, limit)

    status, items, ttl_remaining = cache.read(key)

    if status != "HIT":
        # Cache frio, desligado ou indisponível: a fonte da verdade é o Neo4j.
        query = repository.load_recommendation_query()
        rows = session.execute_read(repository.get_recommendation_rows, user_name, query)
        items = repository.build_recommendations(rows, limit)

        if status == "MISS":
            # Só gravamos quando o cache respondeu e a chave realmente não existia.
            ttl_remaining = cache.write(key, items)

    elapsed_ms = (time.perf_counter() - started) * 1000

    return {
        "user": user_name,
        "total": len(items),
        "cache": status,
        "response_time_ms": round(elapsed_ms, 2),
        "ttl_remaining_seconds": ttl_remaining,
        "recommendations": items,
    }
