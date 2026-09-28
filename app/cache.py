"""Camada de cache em Redis (Parte 3).

Espelha o que app/database.py faz com o Neo4j: o cliente é criado uma única
vez, quando a API inicia, e reaproveitado por todas as requisições. O cliente
do Redis já gerencia um pool de conexões internamente, o que importa quando
vários usuários acessam ao mesmo tempo.

Diferença importante em relação ao Neo4j: o Redis é uma camada de cache, não
a fonte da verdade. Se ele estiver indisponível, a API continua funcionando,
apenas consultando sempre o Neo4j. Por isso as falhas aqui são registradas
no log e devolvidas como estado "DOWN", em vez de virarem erro para o cliente.

Estados possíveis de uma consulta ao cache:
    HIT       a chave estava no Redis; o Neo4j não foi consultado
    MISS      a chave não estava no Redis; o Neo4j foi consultado
    DOWN      o Redis não respondeu; o Neo4j foi consultado
    DISABLED  o cache foi desligado por configuração (cache_enabled=False)
"""
import json
import logging

import redis

from app.config import get_settings

logger = logging.getLogger("app.cache")

# Prefixo das chaves de recomendação: rec:{usuário}:{limite}
KEY_PREFIX = "rec"

_client: redis.Redis | None = None


# ---------------------------------------------------------------- conexão
def init_client() -> redis.Redis:
    """Cria o cliente do Redis. Chamado uma vez, na inicialização da API."""
    global _client
    settings = get_settings()
    _client = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        # Devolve str em vez de bytes, para gravar e ler JSON diretamente.
        decode_responses=True,
        # Se o Redis cair, falha em segundos em vez de deixar a requisição pendurada.
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    return _client


def close_client() -> None:
    """Encerra a conexão. Chamado quando a API é finalizada."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


def get_client() -> redis.Redis | None:
    """Devolve o cliente ativo, ou None se o cache estiver desligado."""
    if not get_settings().cache_enabled:
        return None
    return _client


def ping() -> bool:
    """Verifica se o Redis responde. Nunca lança exceção."""
    try:
        client = _client
        return bool(client is not None and client.ping())
    except redis.RedisError as exc:
        logger.warning("Redis indisponível: %s", exc)
        return False


# ------------------------------------------------------------------ chaves
def build_key(user_name: str, limit: int) -> str:
    """Monta a chave de uma recomendação.

    O limite entra na chave porque pedir 10 filmes e pedir 3 são resultados
    diferentes: guardá-los sob a mesma chave devolveria resposta errada.
    """
    return f"{KEY_PREFIX}:{user_name}:{limit}"


# ----------------------------------------------------------- leitura/escrita
def read(key: str) -> tuple[str, list | None, int | None]:
    """Procura a chave no Redis.

    Devolve (estado, conteúdo, ttl_restante). O conteúdo e o TTL só vêm
    preenchidos quando o estado é HIT.
    """
    if not get_settings().cache_enabled:
        return "DISABLED", None, None

    client = _client
    if client is None:
        return "DOWN", None, None

    try:
        raw = client.get(key)
        if raw is None:
            return "MISS", None, None
        # O TTL é lido junto para que a resposta mostre quanto tempo falta.
        ttl = client.ttl(key)
        return "HIT", json.loads(raw), (ttl if ttl and ttl > 0 else None)
    except (redis.RedisError, json.JSONDecodeError) as exc:
        logger.warning("Falha ao ler o cache (%s): %s", key, exc)
        return "DOWN", None, None


def write(key: str, value: list) -> int | None:
    """Grava o valor no Redis com TTL. Devolve o TTL aplicado, ou None se falhar.

    Usa SETEX, que grava e define a expiração numa única operação: a chave
    nunca fica no Redis sem prazo de validade.
    """
    client = _client
    if client is None:
        return None

    ttl = get_settings().cache_ttl_seconds
    try:
        client.setex(key, ttl, json.dumps(value, ensure_ascii=False))
        return ttl
    except redis.RedisError as exc:
        logger.warning("Falha ao gravar o cache (%s): %s", key, exc)
        return None


# -------------------------------------------------------------- invalidação
def _scan_keys(client: redis.Redis, pattern: str) -> list[str]:
    """Lista as chaves que casam com o padrão.

    Usa SCAN em vez de KEYS: o KEYS percorre todo o banco de uma vez e
    bloqueia o Redis, o que é desaconselhado fora de inspeção manual. O SCAN
    percorre em lotes, sem travar quem está usando o cache ao mesmo tempo.
    """
    return list(client.scan_iter(match=pattern, count=100))


def invalidate_user(user_name: str) -> int:
    """Apaga todas as recomendações de um usuário. Devolve quantas chaves saíram.

    O padrão cobre todos os limites já consultados (rec:Julia:10, rec:Julia:3...),
    porque todos ficaram desatualizados pelo mesmo motivo.
    """
    client = _client
    if client is None:
        return 0

    try:
        keys = _scan_keys(client, f"{KEY_PREFIX}:{user_name}:*")
        if not keys:
            return 0
        removed = client.delete(*keys)
        logger.info("Cache invalidado para '%s': %s chave(s).", user_name, removed)
        return int(removed)
    except redis.RedisError as exc:
        logger.warning("Falha ao invalidar o cache de '%s': %s", user_name, exc)
        return 0


def invalidate_all() -> int:
    """Apaga todas as recomendações em cache. Devolve quantas chaves saíram.

    Remove apenas as chaves com o prefixo da aplicação, nunca o banco inteiro:
    um FLUSHDB apagaria também dados de outros sistemas que usem este Redis.
    """
    client = _client
    if client is None:
        return 0

    try:
        keys = _scan_keys(client, f"{KEY_PREFIX}:*")
        if not keys:
            return 0
        removed = client.delete(*keys)
        logger.info("Cache de recomendações limpo: %s chave(s).", removed)
        return int(removed)
    except redis.RedisError as exc:
        logger.warning("Falha ao limpar o cache: %s", exc)
        return 0


# ------------------------------------------------------------- estatísticas
def stats() -> dict:
    """Estado atual do cache: chaves guardadas e contadores do próprio Redis."""
    settings = get_settings()
    base = {
        "cache_enabled": settings.cache_enabled,
        "ttl_seconds": settings.cache_ttl_seconds,
        "redis": "unavailable",
        "cached_recommendations": 0,
        "keys": [],
    }

    client = _client
    if client is None:
        return base

    try:
        keys = sorted(_scan_keys(client, f"{KEY_PREFIX}:*"))
        info = client.info()
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses
        base.update(
            redis="connected",
            cached_recommendations=len(keys),
            keys=keys,
            # Contadores acumulados do servidor Redis desde que ele subiu.
            keyspace_hits=hits,
            keyspace_misses=misses,
            hit_rate_percent=round(hits / total * 100, 2) if total else 0.0,
            used_memory_human=info.get("used_memory_human"),
            connected_clients=info.get("connected_clients"),
        )
        return base
    except redis.RedisError as exc:
        logger.warning("Falha ao obter estatísticas do cache: %s", exc)
        return base
