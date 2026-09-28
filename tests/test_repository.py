"""Testes da camada repository com uma transação simulada (sem Neo4j)."""
import pytest

from app import repository
from app.config import get_settings
from app.errors import ConflictError, NotFoundError


class Counters:
    def __init__(self, nodes_created=0, relationships_created=0):
        self.nodes_created = nodes_created
        self.relationships_created = relationships_created


class FakeResult:
    def __init__(self, rows, counters):
        self._rows, self._counters = rows, counters

    def data(self):
        return self._rows

    def consume(self):
        return type("Summary", (), {"counters": self._counters})()


class ScriptedTx:
    """Devolve respostas pré-definidas, na ordem, e registra o que foi executado."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def run(self, query, **params):
        self.calls.append((query, params))
        rows, counters = self.responses.pop(0)
        return FakeResult(rows, counters)


def test_recommendation_passes_user_to_userName_and_sends_part1_query_unchanged():
    part1_query = get_settings().recommendation_query_path.read_text(encoding="utf-8-sig")
    tx = ScriptedTx(([{"name": "Carlos"}], Counters()), ([], Counters()))

    repository.get_recommendation_rows(tx, "Carlos", repository.load_recommendation_query())

    query_sent, params = tx.calls[1]
    assert params == {"userName": "Carlos"}
    assert query_sent == part1_query


def test_recommendation_unknown_user_raises_not_found_before_running_query():
    tx = ScriptedTx(([], Counters()))
    with pytest.raises(NotFoundError):
        repository.get_recommendation_rows(tx, "Ninguem", "MATCH (n) RETURN n")
    assert len(tx.calls) == 1  # só a verificação de existência


def test_create_user_conflict_when_no_node_was_created():
    tx = ScriptedTx(([{"name": "Julia"}], Counters(nodes_created=0)))
    with pytest.raises(ConflictError):
        repository.create_user(tx, "Julia")


def test_create_user_ok_when_node_was_created():
    tx = ScriptedTx(([{"name": "Marina"}], Counters(nodes_created=1)))
    assert repository.create_user(tx, "Marina") == {"name": "Marina"}


def test_rating_without_watched_raises_conflict_and_writes_nothing():
    tx = ScriptedTx(
        ([{"name": "Ana"}], Counters()),        # usuário existe
        ([{"title": "Matrix"}], Counters()),    # filme existe
        ([{"total": 0}], Counters()),           # não assistiu
    )
    with pytest.raises(ConflictError):
        repository.register_rating(tx, "Ana", "Matrix", 5)
    assert len(tx.calls) == 3  # nenhum MERGE/SET foi executado


def test_rating_update_reports_created_false():
    tx = ScriptedTx(
        ([{"name": "Ana"}], Counters()),
        ([{"title": "Matrix"}], Counters()),
        ([{"total": 1}], Counters()),
        ([], Counters(relationships_created=0)),  # aresta já existia
    )
    result = repository.register_rating(tx, "Ana", "Matrix", 3)
    assert result["created"] is False and result["rating"] == 3
    assert tx.calls[3][1]["rating"] == 3


def test_create_movie_with_missing_genre_creates_nothing():
    tx = ScriptedTx(([{"name": "Romance"}], Counters()))
    with pytest.raises(NotFoundError):
        repository.create_movie(tx, "Novo", ["Romance", "Inexistente"])
    assert len(tx.calls) == 1  # só a checagem de gêneros
