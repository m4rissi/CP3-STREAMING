"""Configurações da aplicação.

Os valores padrão coincidem com o docker-compose.yml da Parte 1
(Neo4j em localhost:7687, usuário neo4j, senha senha123s) e com o
docker-compose.override.yml da Parte 3 (Redis em localhost:6379),
portanto a API funciona sem nenhuma configuração extra. Para usar outros
valores, defina variáveis de ambiente ou crie um arquivo .env
(veja .env.example).
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Raiz do projeto: a pasta CP3-STREAMING (pai da pasta app/).
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "senha123s"
    neo4j_database: str = "neo4j"

    # --- Redis / cache (Parte 3) ---
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # Tempo de vida (TTL) das recomendações no cache, em segundos.
    cache_ttl_seconds: int = 300

    # Permite desligar o cache sem mexer no código (útil nos testes de desempenho).
    cache_enabled: bool = True

    # A consulta de recomendação da Parte 1 é lida diretamente deste arquivo,
    # sem cópia, para que exista uma única fonte da verdade.
    recommendation_query_path: Path = BASE_DIR / "neo4j" / "recomendacao.cypher"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
