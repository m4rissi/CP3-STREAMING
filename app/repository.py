"""Acesso ao Neo4j: todas as consultas Cypher da API ficam neste arquivo.

Cada função recebe `tx` (uma transação do driver) como primeiro argumento e
é executada pelos endpoints com `session.execute_read(...)` ou
`session.execute_write(...)`. Se uma função levantar NotFoundError ou
ConflictError, a transação é desfeita e o erro chega à API como 404/409.

Os valores nunca são concatenados no texto Cypher: sempre vão como
parâmetros ($nome, $titulo...), o que evita injeção de Cypher.
"""
from functools import lru_cache

from app.config import get_settings
from app.errors import ConflictError, NotFoundError


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------
def _run(tx, query: str, **params):
    """Executa uma consulta e devolve (linhas como dicts, contadores)."""
    result = tx.run(query, **params)
    rows = result.data()
    counters = result.consume().counters
    return rows, counters


def _require_user(tx, name: str) -> None:
    rows, _ = _run(tx, "MATCH (u:User {name: $name}) RETURN u.name AS name", name=name)
    if not rows:
        raise NotFoundError(f"Usuário '{name}' não encontrado.")


def _require_movie(tx, title: str) -> None:
    rows, _ = _run(tx, "MATCH (m:Movie {title: $title}) RETURN m.title AS title", title=title)
    if not rows:
        raise NotFoundError(f"Filme '{title}' não encontrado.")


def _require_genre(tx, name: str) -> None:
    rows, _ = _run(tx, "MATCH (g:Genre {name: $name}) RETURN g.name AS name", name=name)
    if not rows:
        raise NotFoundError(f"Gênero '{name}' não encontrado.")


# ---------------------------------------------------------------------------
# Usuários
# ---------------------------------------------------------------------------
def create_user(tx, name: str) -> dict:
    rows, counters = _run(tx, "MERGE (u:User {name: $name}) RETURN u.name AS name", name=name)
    if counters.nodes_created == 0:
        raise ConflictError(f"Usuário '{name}' já existe.")
    return rows[0]


def list_users(tx) -> list[dict]:
    rows, _ = _run(tx, "MATCH (u:User) RETURN u.name AS name ORDER BY name")
    return rows


def get_user(tx, name: str) -> dict:
    _require_user(tx, name)
    return {"name": name}


# ---------------------------------------------------------------------------
# Gêneros
# ---------------------------------------------------------------------------
def create_genre(tx, name: str) -> dict:
    rows, counters = _run(tx, "MERGE (g:Genre {name: $name}) RETURN g.name AS name", name=name)
    if counters.nodes_created == 0:
        raise ConflictError(f"Gênero '{name}' já existe.")
    return {"name": rows[0]["name"], "movie_count": 0}


def list_genres(tx) -> list[dict]:
    rows, _ = _run(
        tx,
        """
        MATCH (g:Genre)
        OPTIONAL MATCH (m:Movie)-[:HAS_GENRE]->(g)
        RETURN g.name AS name, count(m) AS movie_count
        ORDER BY name
        """,
    )
    return rows


# ---------------------------------------------------------------------------
# Filmes
# ---------------------------------------------------------------------------
def _movie_with_genres(tx, title: str) -> dict:
    rows, _ = _run(
        tx,
        """
        MATCH (m:Movie {title: $title})
        OPTIONAL MATCH (m)-[:HAS_GENRE]->(g:Genre)
        RETURN m.title AS title, collect(g.name) AS genres
        """,
        title=title,
    )
    if not rows:
        raise NotFoundError(f"Filme '{title}' não encontrado.")
    return {"title": rows[0]["title"], "genres": sorted(rows[0]["genres"])}


def create_movie(tx, title: str, genres: list[str]) -> dict:
    # 1) Todos os gêneros informados precisam existir.
    if genres:
        rows, _ = _run(
            tx,
            "MATCH (g:Genre) WHERE g.name IN $genres RETURN g.name AS name",
            genres=genres,
        )
        found = {r["name"] for r in rows}
        missing = [g for g in genres if g not in found]
        if missing:
            raise NotFoundError(f"Gênero(s) não encontrado(s): {', '.join(missing)}.")

    # 2) Cria o filme (MERGE não duplica; sem nó criado = já existia).
    _, counters = _run(tx, "MERGE (m:Movie {title: $title}) RETURN m.title AS title", title=title)
    if counters.nodes_created == 0:
        raise ConflictError(f"Filme '{title}' já existe.")

    # 3) Liga o filme aos gêneros (HAS_GENRE).
    if genres:
        _run(
            tx,
            """
            MATCH (m:Movie {title: $title})
            UNWIND $genres AS genreName
            MATCH (g:Genre {name: genreName})
            MERGE (m)-[:HAS_GENRE]->(g)
            """,
            title=title,
            genres=genres,
        )
    return _movie_with_genres(tx, title)


def add_genre_to_movie(tx, title: str, genre: str) -> dict:
    _require_movie(tx, title)
    _require_genre(tx, genre)
    _run(
        tx,
        """
        MATCH (m:Movie {title: $title}), (g:Genre {name: $genre})
        MERGE (m)-[:HAS_GENRE]->(g)
        """,
        title=title,
        genre=genre,
    )
    return _movie_with_genres(tx, title)


def get_movie(tx, title: str) -> dict:
    return _movie_with_genres(tx, title)


def list_movies(tx) -> list[dict]:
    rows, _ = _run(
        tx,
        """
        MATCH (m:Movie)
        OPTIONAL MATCH (m)-[:HAS_GENRE]->(g:Genre)
        RETURN m.title AS title, collect(g.name) AS genres
        ORDER BY title
        """,
    )
    return [{"title": r["title"], "genres": sorted(r["genres"])} for r in rows]


# ---------------------------------------------------------------------------
# Filmes assistidos (WATCHED)
# ---------------------------------------------------------------------------
def register_watched(tx, user_name: str, movie_title: str) -> dict:
    """Registra WATCHED. `created` é False se o registro já existia."""
    _require_user(tx, user_name)
    _require_movie(tx, movie_title)
    _, counters = _run(
        tx,
        """
        MATCH (u:User {name: $userName}), (m:Movie {title: $title})
        MERGE (u)-[:WATCHED]->(m)
        """,
        userName=user_name,
        title=movie_title,
    )
    return {
        "user": user_name,
        "movie_title": movie_title,
        "created": counters.relationships_created > 0,
    }


def list_watched(tx, user_name: str) -> list[dict]:
    _require_user(tx, user_name)
    rows, _ = _run(
        tx,
        """
        MATCH (u:User {name: $userName})-[:WATCHED]->(m:Movie)
        RETURN m.title AS title
        ORDER BY title
        """,
        userName=user_name,
    )
    return [{"user": user_name, "movie_title": r["title"]} for r in rows]


# ---------------------------------------------------------------------------
# Avaliações (RATED)
# ---------------------------------------------------------------------------
def register_rating(tx, user_name: str, movie_title: str, rating: int) -> dict:
    """Registra ou atualiza a nota. Só é possível avaliar filme já assistido."""
    _require_user(tx, user_name)
    _require_movie(tx, movie_title)

    watched, _ = _run(
        tx,
        """
        MATCH (:User {name: $userName})-[w:WATCHED]->(:Movie {title: $title})
        RETURN count(w) AS total
        """,
        userName=user_name,
        title=movie_title,
    )
    if watched[0]["total"] == 0:
        raise ConflictError(
            f"'{user_name}' ainda não assistiu '{movie_title}'. "
            "Registre o filme como assistido antes de avaliar."
        )

    # MERGE sem a nota no padrão: se já existir uma avaliação, ela é
    # atualizada (SET) em vez de criar uma segunda aresta RATED.
    _, counters = _run(
        tx,
        """
        MATCH (u:User {name: $userName}), (m:Movie {title: $title})
        MERGE (u)-[r:RATED]->(m)
        SET r.rating = $rating
        """,
        userName=user_name,
        title=movie_title,
        rating=rating,
    )
    return {
        "user": user_name,
        "movie_title": movie_title,
        "rating": rating,
        "created": counters.relationships_created > 0,
    }


def list_ratings(tx, user_name: str) -> list[dict]:
    _require_user(tx, user_name)
    rows, _ = _run(
        tx,
        """
        MATCH (u:User {name: $userName})-[r:RATED]->(m:Movie)
        RETURN m.title AS title, r.rating AS rating
        ORDER BY title
        """,
        userName=user_name,
    )
    return [{"user": user_name, "movie_title": r["title"], "rating": r["rating"]} for r in rows]


# ---------------------------------------------------------------------------
# Recomendações
# ---------------------------------------------------------------------------
@lru_cache
def load_recommendation_query() -> str:
    """Lê a consulta da Parte 1 (neo4j/recomendacao.cypher), sem alterá-la."""
    path = get_settings().recommendation_query_path
    if not path.is_file():
        raise FileNotFoundError(f"Consulta de recomendação não encontrada em: {path}")
    return path.read_text(encoding="utf-8-sig")


def get_recommendation_rows(tx, user_name: str, query: str) -> list[dict]:
    """Passa o usuário recebido pela API ao parâmetro $userName da consulta."""
    _require_user(tx, user_name)
    rows, _ = _run(tx, query, userName=user_name)
    return rows


def build_recommendations(rows: list[dict], limit: int) -> list[dict]:
    """Converte as linhas da consulta no formato da API.

    A consulta devolve uma linha por (filme, usuário de referência), já
    ordenada do melhor para o pior. Se o mesmo filme aparecer com mais de um
    usuário de referência, mantemos apenas a primeira ocorrência (a melhor).
    """
    seen: set[str] = set()
    items: list[dict] = []
    for row in rows:
        title = row["filme_recomendado"]
        if title in seen:
            continue
        seen.add(title)
        items.append(
            {
                "filme_recomendado": title,
                "usuario_referencia": row["usuario_referencia"],
                "filmes_em_comum": row["filmesEmComum"],
                "media_notas": row["media_notas"],
            }
        )
        if len(items) >= limit:
            break
    return items
