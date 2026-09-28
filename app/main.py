"""Ponto de entrada da API.

Fluxo da Parte 3:  FastAPI  ->  Redis (cache)  ->  Neo4j

Nesta etapa o Redis é apenas conectado e monitorado pelo /health; o cache
das recomendações é implementado na etapa seguinte.

Executar (na pasta CP3-STREAMING):
    uvicorn app.main:app --reload
Documentação interativa: http://127.0.0.1:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from neo4j.exceptions import AuthError, ConstraintError, ServiceUnavailable, SessionExpired

from app import cache, database, repository
from app.config import get_settings
from app.errors import AppError
from app.routers import cache_admin, genres, movies, recommendations, users

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Falha cedo se o arquivo da consulta de recomendação não existir.
    repository.load_recommendation_query()

    driver = database.init_driver()
    try:
        driver.verify_connectivity()
        logger.info("Conectado ao Neo4j.")
    except Exception as exc:  # a API sobe mesmo assim; /health mostrará o problema
        logger.warning("Não foi possível conectar ao Neo4j agora: %s", exc)

    # O Redis é opcional: se não conectar, a API continua servindo pelo Neo4j.
    cache.init_client()
    if cache.ping():
        logger.info("Conectado ao Redis.")
    else:
        logger.warning("Redis indisponível; a API responderá sempre pelo Neo4j.")

    yield

    cache.close_client()
    database.close_driver()


app = FastAPI(
    title="Plataforma de Recomendação - Streaming (CP3)",
    description="API REST em FastAPI que usa o Neo4j para cadastrar usuários, filmes e "
                "gêneros, registrar filmes assistidos e avaliações, e gerar recomendações "
                "personalizadas, com o Redis como camada de cache (Parte 3).",
    version="3.0.0",
    lifespan=lifespan,
)

app.include_router(users.router)
app.include_router(movies.router)
app.include_router(genres.router)
app.include_router(recommendations.router)
app.include_router(cache_admin.router)


# ---------- Tratamento de erros ----------
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


@app.exception_handler(ConstraintError)
async def constraint_error_handler(request: Request, exc: ConstraintError):
    # Duplicidade detectada pelas constraints do Neo4j (ex.: duas requisições simultâneas).
    return JSONResponse(status_code=409, content={"detail": "Registro já existe."})


async def neo4j_unavailable_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=503,
        content={"detail": "Não foi possível acessar o Neo4j. Verifique se o container "
                           "está em execução (docker compose up -d) e as credenciais."},
    )


for _exc in (ServiceUnavailable, SessionExpired, AuthError):
    app.add_exception_handler(_exc, neo4j_unavailable_handler)


# ---------- Rotas gerais ----------
@app.get("/", tags=["Geral"], summary="Informações da API")
def root():
    return {"name": app.title, "version": app.version, "docs": "/docs", "health": "/health"}


@app.get("/health", tags=["Geral"], summary="Verifica a conexão com o Neo4j e o Redis")
def health():
    settings = get_settings()
    database.get_driver().verify_connectivity()  # se falhar, o handler devolve 503

    if not settings.cache_enabled:
        redis_status = "disabled"
    else:
        redis_status = "connected" if cache.ping() else "unavailable"

    return {
        "status": "ok",
        "neo4j": "connected",
        "redis": redis_status,
        "cache_ttl_seconds": settings.cache_ttl_seconds,
    }
