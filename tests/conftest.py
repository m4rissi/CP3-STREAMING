"""Fixtures dos testes automatizados.

Estes testes NÃO precisam do Neo4j: o repositório é substituído por uma
versão em memória. Eles validam a camada HTTP (rotas, validação, códigos de
status, mensagens de erro). As consultas Cypher em si são validadas pelo
tests/smoke_test.py, executado contra o Neo4j real.
"""
import pytest
from fastapi.testclient import TestClient

from app import repository
from app.database import get_session
from app.errors import ConflictError, NotFoundError
from app.main import app


class FakeSession:
    """Imita session.execute_read/execute_write chamando a função sem transação."""

    def execute_read(self, fn, *args, **kwargs):
        return fn(None, *args, **kwargs)

    execute_write = execute_read


class FakeGraph:
    def __init__(self):
        self.users = {"Julia", "Carlos", "Ana"}
        self.genres = {"Ficção Científica", "Fantasia", "Animação", "Romance"}
        self.movies = {
            "Interestelar": {"Ficção Científica"},
            "Matrix": {"Ficção Científica"},
            "O Senhor dos Anéis": {"Fantasia"},
            "Toy Story": {"Animação"},
            "Titanic": {"Romance"},
        }
        self.watched = {("Julia", "Interestelar"), ("Julia", "Matrix")}
        self.ratings = {("Julia", "Interestelar"): 5, ("Julia", "Matrix"): 5}
        self.last_recommendation_user = None

    # --- helpers
    def _user(self, n):
        if n not in self.users:
            raise NotFoundError(f"Usuário '{n}' não encontrado.")

    def _movie(self, t):
        if t not in self.movies:
            raise NotFoundError(f"Filme '{t}' não encontrado.")

    def _genre(self, g):
        if g not in self.genres:
            raise NotFoundError(f"Gênero '{g}' não encontrado.")

    # --- usuários
    def create_user(self, tx, name):
        if name in self.users:
            raise ConflictError(f"Usuário '{name}' já existe.")
        self.users.add(name)
        return {"name": name}

    def list_users(self, tx):
        return [{"name": n} for n in sorted(self.users)]

    def get_user(self, tx, name):
        self._user(name)
        return {"name": name}

    # --- gêneros
    def create_genre(self, tx, name):
        if name in self.genres:
            raise ConflictError(f"Gênero '{name}' já existe.")
        self.genres.add(name)
        return {"name": name, "movie_count": 0}

    def list_genres(self, tx):
        return [
            {"name": g, "movie_count": sum(g in gs for gs in self.movies.values())}
            for g in sorted(self.genres)
        ]

    # --- filmes
    def create_movie(self, tx, title, genres):
        missing = [g for g in genres if g not in self.genres]
        if missing:
            raise NotFoundError(f"Gênero(s) não encontrado(s): {', '.join(missing)}.")
        if title in self.movies:
            raise ConflictError(f"Filme '{title}' já existe.")
        self.movies[title] = set(genres)
        return {"title": title, "genres": sorted(genres)}

    def get_movie(self, tx, title):
        self._movie(title)
        return {"title": title, "genres": sorted(self.movies[title])}

    def list_movies(self, tx):
        return [{"title": t, "genres": sorted(g)} for t, g in sorted(self.movies.items())]

    def add_genre_to_movie(self, tx, title, genre):
        self._movie(title)
        self._genre(genre)
        self.movies[title].add(genre)
        return self.get_movie(tx, title)

    # --- assistidos / avaliações
    def register_watched(self, tx, user, title):
        self._user(user)
        self._movie(title)
        created = (user, title) not in self.watched
        self.watched.add((user, title))
        return {"user": user, "movie_title": title, "created": created}

    def list_watched(self, tx, user):
        self._user(user)
        return [{"user": u, "movie_title": t} for u, t in sorted(self.watched) if u == user]

    def register_rating(self, tx, user, title, rating):
        self._user(user)
        self._movie(title)
        if (user, title) not in self.watched:
            raise ConflictError(f"'{user}' ainda não assistiu '{title}'.")
        created = (user, title) not in self.ratings
        self.ratings[(user, title)] = rating
        return {"user": user, "movie_title": title, "rating": rating, "created": created}

    def list_ratings(self, tx, user):
        self._user(user)
        return [
            {"user": u, "movie_title": t, "rating": r}
            for (u, t), r in sorted(self.ratings.items())
            if u == user
        ]

    # --- recomendação (devolve linhas no formato da consulta real)
    def get_recommendation_rows(self, tx, user, query):
        self._user(user)
        self.last_recommendation_user = user
        assert "$userName" in query  # a consulta recebida é a parametrizada da Parte 1
        if user == "Julia":
            return [{
                "filme_recomendado": "O Senhor dos Anéis",
                "usuario_referencia": "Carlos",
                "filmesEmComum": 2,
                "media_notas": 4.5,
            }]
        return []


@pytest.fixture
def graph(monkeypatch):
    g = FakeGraph()
    for name in (
        "create_user list_users get_user create_genre list_genres create_movie get_movie "
        "list_movies add_genre_to_movie register_watched list_watched register_rating "
        "list_ratings get_recommendation_rows"
    ).split():
        monkeypatch.setattr(repository, name, getattr(g, name))
    app.dependency_overrides[get_session] = lambda: FakeSession()
    yield g
    app.dependency_overrides.clear()


@pytest.fixture
def client(graph):
    # Sem "with": o lifespan (que conecta ao Neo4j) não é executado nos testes.
    return TestClient(app)
