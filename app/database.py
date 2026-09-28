"""Conexão com o Neo4j.

O driver é criado uma única vez, quando a API inicia, e reaproveitado por
todas as requisições. Cada requisição recebe sua própria sessão, que é
fechada ao final.
"""
import logging
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from neo4j import Driver, GraphDatabase, Session

from app.config import get_settings

logger = logging.getLogger("app.database")

_driver: Driver | None = None


def init_driver() -> Driver:
    global _driver
    settings = get_settings()
    _driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        # Se o Neo4j cair, responde 503 em poucos segundos em vez de deixar a
        # requisição pendurada (o padrão do driver é tentar de novo por 30 s).
        connection_timeout=5,
        max_transaction_retry_time=3,
    )
    return _driver


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def get_driver() -> Driver:
    if _driver is None:
        raise RuntimeError("Driver do Neo4j não inicializado.")
    return _driver


def get_session() -> Iterator[Session]:
    """Dependência do FastAPI: uma sessão do Neo4j por requisição."""
    with get_driver().session(database=get_settings().neo4j_database) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
