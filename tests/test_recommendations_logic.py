"""Testes da conversão das linhas da consulta em itens da API."""
from app.repository import build_recommendations


def row(filme, ref, comum, media):
    return {"filme_recomendado": filme, "usuario_referencia": ref,
            "filmesEmComum": comum, "media_notas": media}


def test_maps_query_columns_to_api_fields():
    items = build_recommendations([row("O Senhor dos Anéis", "Carlos", 2, 4.5)], 10)
    assert items == [{
        "filme_recomendado": "O Senhor dos Anéis",
        "usuario_referencia": "Carlos",
        "filmes_em_comum": 2,
        "media_notas": 4.5,
    }]


def test_same_movie_from_two_references_keeps_the_best_one():
    rows = [row("A", "Carlos", 3, 4.8), row("B", "Ana", 2, 4.0), row("A", "Julia", 1, 3.0)]
    items = build_recommendations(rows, 10)
    assert [i["filme_recomendado"] for i in items] == ["A", "B"]
    assert items[0]["usuario_referencia"] == "Carlos"


def test_limit_and_order_are_respected():
    rows = [row(f"F{i}", "X", 10 - i, 5.0) for i in range(5)]
    items = build_recommendations(rows, 3)
    assert [i["filme_recomendado"] for i in items] == ["F0", "F1", "F2"]


def test_empty_rows():
    assert build_recommendations([], 10) == []
