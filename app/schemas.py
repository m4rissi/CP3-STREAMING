"""Modelos Pydantic: definem e validam o que entra e o que sai da API."""
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

# Nome/título: sem espaços nas pontas, de 1 a 100 caracteres e sem "/" ou "\"
# (esses caracteres quebrariam as URLs do tipo /users/{nome}/...).
Text = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
        pattern=r"^[^/\\]+$",
    ),
]


# ---------- Usuários ----------
class UserCreate(BaseModel):
    name: Text = Field(examples=["Marina"])


class UserOut(BaseModel):
    name: str


# ---------- Gêneros ----------
class GenreCreate(BaseModel):
    name: Text = Field(examples=["Suspense"])


class GenreOut(BaseModel):
    name: str
    movie_count: int = 0


# ---------- Filmes ----------
class MovieCreate(BaseModel):
    title: Text = Field(examples=["Divertida Mente"])
    genres: list[Text] = Field(
        default_factory=list,
        description="Nomes de gêneros já cadastrados (opcional).",
        examples=[["Animação"]],
    )

    @field_validator("genres")
    @classmethod
    def remove_duplicates(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class MovieGenreAdd(BaseModel):
    genre: Text = Field(examples=["Fantasia"])


class MovieOut(BaseModel):
    title: str
    genres: list[str] = []


# ---------- Assistidos e avaliações ----------
class WatchedCreate(BaseModel):
    movie_title: Text = Field(examples=["Matrix"])


class WatchedOut(BaseModel):
    user: str
    movie_title: str


class WatchedRegisterOut(WatchedOut):
    """Resposta do registro de filme assistido, com o efeito no cache."""

    cache_invalidated: int = Field(
        default=0,
        description="Quantidade de recomendações do usuário removidas do cache.",
        examples=[1],
    )


class RatingCreate(BaseModel):
    movie_title: Text = Field(examples=["Matrix"])
    rating: int = Field(ge=1, le=5, description="Nota de 1 a 5.", examples=[5])


class RatingOut(BaseModel):
    user: str | None = None
    movie_title: str
    rating: int


class RatingRegisterOut(RatingOut):
    """Resposta do registro de avaliação, com o efeito no cache."""

    cache_invalidated: int = Field(
        default=0,
        description="Quantidade de recomendações do usuário removidas do cache.",
        examples=[1],
    )


# ---------- Recomendações ----------
class RecommendationItem(BaseModel):
    filme_recomendado: str
    usuario_referencia: str
    filmes_em_comum: int
    media_notas: float


class RecommendationResponse(BaseModel):
    user: str
    total: int
    cache: Literal["HIT", "MISS", "DOWN", "DISABLED"] = Field(
        description=(
            "HIT: resposta veio do Redis (o Neo4j não foi consultado). "
            "MISS: não estava no cache; foi consultado o Neo4j e o resultado foi "
            "gravado. DOWN: o Redis não respondeu; a resposta veio do Neo4j. "
            "DISABLED: cache desligado por configuração."
        ),
        examples=["HIT"],
    )
    response_time_ms: float = Field(
        description="Tempo de processamento da requisição, em milissegundos.",
        examples=[1.83],
    )
    ttl_remaining_seconds: int | None = Field(
        default=None,
        description="Tempo restante até a recomendação expirar no cache.",
        examples=[284],
    )
    recommendations: list[RecommendationItem]


# ---------- Cache (Parte 3) ----------
class CacheInvalidationOut(BaseModel):
    user: str | None = Field(
        default=None,
        description="Usuário afetado; nulo quando todo o cache foi limpo.",
    )
    keys_removed: int = Field(description="Quantidade de chaves removidas do Redis.")


class CacheStatsOut(BaseModel):
    cache_enabled: bool
    ttl_seconds: int
    redis: str
    cached_recommendations: int = Field(description="Chaves rec:* guardadas no momento.")
    keys: list[str] = []
    keyspace_hits: int | None = None
    keyspace_misses: int | None = None
    hit_rate_percent: float | None = None
    used_memory_human: str | None = None
    connected_clients: int | None = None
