"""Testes da camada HTTP (sem Neo4j)."""


# ---------- usuários ----------
def test_create_user_returns_201(client):
    r = client.post("/users", json={"name": "Marina"})
    assert r.status_code == 201
    assert r.json() == {"name": "Marina"}


def test_create_user_strips_spaces(client):
    r = client.post("/users", json={"name": "  Marina  "})
    assert r.status_code == 201
    assert r.json()["name"] == "Marina"


def test_create_duplicate_user_returns_409(client):
    r = client.post("/users", json={"name": "Julia"})
    assert r.status_code == 409
    assert "já existe" in r.json()["detail"]


def test_create_user_invalid_name_returns_422(client):
    assert client.post("/users", json={"name": ""}).status_code == 422
    assert client.post("/users", json={"name": "   "}).status_code == 422
    assert client.post("/users", json={"name": "a/b"}).status_code == 422
    assert client.post("/users", json={}).status_code == 422


def test_list_and_get_user(client):
    assert [u["name"] for u in client.get("/users").json()] == ["Ana", "Carlos", "Julia"]
    assert client.get("/users/Julia").json() == {"name": "Julia"}
    assert client.get("/users/Ninguem").status_code == 404


# ---------- gêneros ----------
def test_create_genre_and_duplicate(client):
    r = client.post("/genres", json={"name": "Suspense"})
    assert r.status_code == 201
    assert r.json() == {"name": "Suspense", "movie_count": 0}
    assert client.post("/genres", json={"name": "Suspense"}).status_code == 409


def test_list_genres_has_movie_count(client):
    genres = {g["name"]: g["movie_count"] for g in client.get("/genres").json()}
    assert genres["Ficção Científica"] == 2
    assert genres["Romance"] == 1


# ---------- filmes ----------
def test_create_movie_with_genres(client):
    r = client.post("/movies", json={"title": "Divertida Mente", "genres": ["Animação"]})
    assert r.status_code == 201
    assert r.json() == {"title": "Divertida Mente", "genres": ["Animação"]}


def test_create_movie_without_genres(client):
    r = client.post("/movies", json={"title": "Filme Solto"})
    assert r.status_code == 201
    assert r.json()["genres"] == []


def test_create_movie_removes_duplicate_genres(client):
    r = client.post("/movies", json={"title": "X", "genres": ["Romance", "Romance"]})
    assert r.json()["genres"] == ["Romance"]


def test_create_movie_unknown_genre_returns_404(client, graph):
    r = client.post("/movies", json={"title": "Novo", "genres": ["Inexistente"]})
    assert r.status_code == 404
    assert "Inexistente" in r.json()["detail"]
    assert "Novo" not in graph.movies


def test_create_duplicate_movie_returns_409(client):
    assert client.post("/movies", json={"title": "Matrix"}).status_code == 409


def test_get_movie_with_accents_and_spaces(client):
    r = client.get("/movies/O Senhor dos Anéis")
    assert r.status_code == 200
    assert r.json() == {"title": "O Senhor dos Anéis", "genres": ["Fantasia"]}
    assert client.get("/movies/Inexistente").status_code == 404


def test_add_genre_to_movie(client):
    r = client.post("/movies/Matrix/genres", json={"genre": "Fantasia"})
    assert r.status_code == 200
    assert r.json()["genres"] == ["Fantasia", "Ficção Científica"]
    assert client.post("/movies/Matrix/genres", json={"genre": "Nada"}).status_code == 404
    assert client.post("/movies/Nada/genres", json={"genre": "Romance"}).status_code == 404


def test_list_movies(client):
    titles = [m["title"] for m in client.get("/movies").json()]
    assert "Interestelar" in titles and len(titles) == 5


# ---------- assistidos ----------
def test_register_watched_201_then_200(client):
    r = client.post("/users/Ana/watched", json={"movie_title": "Matrix"})
    assert r.status_code == 201
    # cache_invalidated: quantas recomendações do usuário saíram do Redis (0 sem Redis).
    assert r.json() == {"user": "Ana", "movie_title": "Matrix", "cache_invalidated": 0}
    r2 = client.post("/users/Ana/watched", json={"movie_title": "Matrix"})
    assert r2.status_code == 200


def test_register_watched_unknown_user_or_movie(client):
    assert client.post("/users/Nada/watched", json={"movie_title": "Matrix"}).status_code == 404
    assert client.post("/users/Ana/watched", json={"movie_title": "Nada"}).status_code == 404


def test_list_watched(client):
    titles = [w["movie_title"] for w in client.get("/users/Julia/watched").json()]
    assert titles == ["Interestelar", "Matrix"]
    assert client.get("/users/Nada/watched").status_code == 404


# ---------- avaliações ----------
def test_rating_requires_watched(client):
    r = client.post("/users/Ana/ratings", json={"movie_title": "Matrix", "rating": 4})
    assert r.status_code == 409


def test_rating_create_then_update(client):
    client.post("/users/Ana/watched", json={"movie_title": "Matrix"})
    r = client.post("/users/Ana/ratings", json={"movie_title": "Matrix", "rating": 4})
    assert r.status_code == 201
    assert r.json() == {"user": "Ana", "movie_title": "Matrix", "rating": 4,
                        "cache_invalidated": 0}
    r2 = client.post("/users/Ana/ratings", json={"movie_title": "Matrix", "rating": 2})
    assert r2.status_code == 200
    ratings = client.get("/users/Ana/ratings").json()
    assert ratings == [{"user": "Ana", "movie_title": "Matrix", "rating": 2}]


def test_rating_out_of_range_returns_422(client):
    for bad in (0, 6, -1):
        r = client.post("/users/Julia/ratings", json={"movie_title": "Matrix", "rating": bad})
        assert r.status_code == 422
    r = client.post("/users/Julia/ratings", json={"movie_title": "Matrix"})
    assert r.status_code == 422


# ---------- recomendações ----------
def sem_campos_de_cache(body: dict) -> dict:
    """Remove os campos da Parte 3 para comparar só o conteúdo da recomendação.

    O tempo de resposta varia a cada execução e o estado do cache depende do
    Redis, que não participa destes testes (eles não usam o lifespan).
    """
    body = dict(body)
    body.pop("response_time_ms")
    body.pop("ttl_remaining_seconds")
    assert body.pop("cache") in {"HIT", "MISS", "DOWN", "DISABLED"}
    return body


def test_recommendation_for_julia(client):
    r = client.get("/users/Julia/recommendations")
    assert r.status_code == 200
    assert sem_campos_de_cache(r.json()) == {
        "user": "Julia",
        "total": 1,
        "recommendations": [{
            "filme_recomendado": "O Senhor dos Anéis",
            "usuario_referencia": "Carlos",
            "filmes_em_comum": 2,
            "media_notas": 4.5,
        }],
    }


def test_recommendation_uses_user_from_url(client, graph):
    """A lógica não fica presa à Julia: o usuário da URL é o que vai à consulta."""
    r = client.get("/users/Ana/recommendations")
    assert r.status_code == 200
    assert graph.last_recommendation_user == "Ana"
    assert sem_campos_de_cache(r.json()) == {"user": "Ana", "total": 0, "recommendations": []}


def test_recommendation_unknown_user_returns_404(client):
    assert client.get("/users/Ninguem/recommendations").status_code == 404


def test_recommendation_limit_validation(client):
    assert client.get("/users/Julia/recommendations?limit=0").status_code == 422
    assert client.get("/users/Julia/recommendations?limit=51").status_code == 422
    assert client.get("/users/Julia/recommendations?limit=5").status_code == 200


def test_recommendation_query_is_the_part1_file():
    """A API usa o recomendacao.cypher da Parte 1, com o parâmetro $userName."""
    from app import repository
    query = repository.load_recommendation_query()
    assert "$userName" in query
    assert "filme_recomendado" in query
