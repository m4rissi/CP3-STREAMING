"""Teste de ponta a ponta:  requisição HTTP -> FastAPI -> Python -> Neo4j.

Diferente dos testes do pytest (que simulam o banco), este script usa a API
em execução e o Neo4j real, validando de fato as consultas Cypher.

Como usar (com o Neo4j e a API já rodando, na pasta CP3-STREAMING):
    python tests/smoke_test.py
    python tests/smoke_test.py --url http://127.0.0.1:8000

Segurança dos dados: tudo que o teste cria usa o prefixo "smoke_teste_" e é
apagado no final (somente esses registros). Julia, Carlos, Ana e os filmes e
gêneros da Parte 1 não são alterados nem apagados.
"""
import argparse
import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RUN = uuid.uuid4().hex[:6]
PREFIX = "smoke_teste_"
USER = f"{PREFIX}usuario_{RUN}"
MOVIE = f"{PREFIX}filme_{RUN}"
GENRE = f"{PREFIX}genero_{RUN}"

results: list[tuple[bool, str]] = []


def check(description: str, condition: bool, detail: str = "") -> None:
    results.append((condition, description))
    print(f"  [{'OK' if condition else 'FALHOU'}] {description}" + (f"  -> {detail}" if not condition and detail else ""))


def cleanup() -> None:
    """Apaga somente os registros criados por este teste (prefixo smoke_teste_)."""
    from neo4j import GraphDatabase

    from app.config import get_settings

    s = get_settings()
    driver = GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))
    with driver.session(database=s.neo4j_database) as session:
        session.run(
            """
            MATCH (n)
            WHERE (n:User OR n:Movie OR n:Genre)
              AND (n.name STARTS WITH $p OR n.title STARTS WITH $p)
            DETACH DELETE n
            """,
            p=PREFIX,
        ).consume()
    driver.close()


def run(base_url: str) -> None:
    c = httpx.Client(base_url=base_url, timeout=30)

    print("\n1) Conexão")
    r = c.get("/health")
    check("GET /health -> 200 (API conectada ao Neo4j)", r.status_code == 200, r.text)
    if r.status_code != 200:
        raise SystemExit("API ou Neo4j indisponível. Interrompendo.")

    print("\n2) Dados da Parte 1 e recomendação para a Julia")
    names = [u["name"] for u in c.get("/users").json()]
    check("Usuários Julia, Carlos e Ana existem", {"Julia", "Carlos", "Ana"} <= set(names), str(names))
    r = c.get("/users/Julia/recommendations")
    body = r.json() if r.status_code == 200 else {}
    recs = body.get("recommendations", [])
    check("GET /users/Julia/recommendations -> 200", r.status_code == 200, r.text)
    check(
        "Julia recebe 'O Senhor dos Anéis' (ref. Carlos, 2 em comum, média 4.5)",
        bool(recs)
        and recs[0]["filme_recomendado"] == "O Senhor dos Anéis"
        and recs[0]["usuario_referencia"] == "Carlos"
        and recs[0]["filmes_em_comum"] == 2
        and recs[0]["media_notas"] == 4.5,
        str(recs),
    )

    print("\n3) Cadastros (usuário, gênero, filme)")
    check("POST /users -> 201", c.post("/users", json={"name": USER}).status_code == 201)
    check("POST /users duplicado -> 409", c.post("/users", json={"name": USER}).status_code == 409)
    check("POST /genres -> 201", c.post("/genres", json={"name": GENRE}).status_code == 201)
    check("POST /genres duplicado -> 409", c.post("/genres", json={"name": GENRE}).status_code == 409)
    r = c.post("/movies", json={"title": MOVIE, "genres": [GENRE]})
    check("POST /movies com gênero -> 201", r.status_code == 201 and r.json()["genres"] == [GENRE], r.text)
    check("POST /movies duplicado -> 409", c.post("/movies", json={"title": MOVIE}).status_code == 409)
    r = c.post("/movies", json={"title": f"{PREFIX}x_{RUN}", "genres": ["Gênero Que Não Existe"]})
    check("POST /movies com gênero inexistente -> 404", r.status_code == 404, r.text)
    r = c.get(f"/movies/{MOVIE}")
    check("GET /movies/{título} -> 200", r.status_code == 200 and r.json()["title"] == MOVIE, r.text)
    r = c.get("/genres")
    check(
        "GET /genres mostra o gênero com 1 filme",
        any(g["name"] == GENRE and g["movie_count"] == 1 for g in r.json()),
        r.text,
    )
    r = c.post("/movies/Matrix/genres", json={"genre": "Ficção Científica"})
    check("POST /movies/Matrix/genres (já associado) -> 200, sem duplicar", r.status_code == 200
          and r.json()["genres"].count("Ficção Científica") == 1, r.text)

    print("\n4) Filmes assistidos")
    r = c.post(f"/users/{USER}/watched", json={"movie_title": "Interestelar"})
    check("POST watched Interestelar -> 201", r.status_code == 201, r.text)
    r = c.post(f"/users/{USER}/watched", json={"movie_title": "Interestelar"})
    check("POST watched repetido -> 200 (sem duplicar)", r.status_code == 200, r.text)
    check("POST watched do filme de teste -> 201",
          c.post(f"/users/{USER}/watched", json={"movie_title": MOVIE}).status_code == 201)
    r = c.post(f"/users/{USER}/watched", json={"movie_title": "Filme Que Não Existe"})
    check("POST watched com filme inexistente -> 404", r.status_code == 404, r.text)
    r = c.post("/users/Usuario Que Nao Existe/watched", json={"movie_title": "Matrix"})
    check("POST watched com usuário inexistente -> 404", r.status_code == 404, r.text)
    watched = [w["movie_title"] for w in c.get(f"/users/{USER}/watched").json()]
    check("GET watched lista exatamente 2 filmes", sorted(watched) == sorted(["Interestelar", MOVIE]), str(watched))

    print("\n5) Avaliações")
    r = c.post(f"/users/{USER}/ratings", json={"movie_title": "Matrix", "rating": 4})
    check("Avaliar filme NÃO assistido -> 409", r.status_code == 409, r.text)
    r = c.post(f"/users/{USER}/ratings", json={"movie_title": MOVIE, "rating": 5})
    check("POST ratings -> 201", r.status_code == 201 and r.json()["rating"] == 5, r.text)
    r = c.post(f"/users/{USER}/ratings", json={"movie_title": MOVIE, "rating": 3})
    check("POST ratings de novo -> 200 (atualiza)", r.status_code == 200, r.text)
    ratings = c.get(f"/users/{USER}/ratings").json()
    check("Apenas 1 avaliação, com a nota atualizada (3)",
          len(ratings) == 1 and ratings[0]["rating"] == 3, str(ratings))
    check("Nota 6 -> 422",
          c.post(f"/users/{USER}/ratings", json={"movie_title": MOVIE, "rating": 6}).status_code == 422)

    print("\n6) Recomendação para outro usuário (prova que não está presa à Julia)")
    r = c.get(f"/users/{USER}/recommendations")
    titles = [i["filme_recomendado"] for i in r.json().get("recommendations", [])] if r.status_code == 200 else []
    check("GET recommendations do usuário de teste -> 200", r.status_code == 200, r.text)
    check("Recebe 'Matrix' e 'O Senhor dos Anéis' (assistiu Interestelar como Julia e Carlos)",
          {"Matrix", "O Senhor dos Anéis"} <= set(titles), str(titles))
    check("Não recebe filmes que já assistiu", "Interestelar" not in titles and MOVIE not in titles, str(titles))
    r = c.get("/users/Carlos/recommendations")
    check("GET recommendations do Carlos -> 200", r.status_code == 200, r.text)
    r = c.get(f"/users/{USER}/recommendations?limit=1")
    check("Parâmetro limit=1 devolve no máximo 1 filme",
          r.status_code == 200 and len(r.json()["recommendations"]) <= 1, r.text)
    r = c.get("/users/Usuario Que Nao Existe/recommendations")
    check("Recomendação para usuário inexistente -> 404", r.status_code == 404, r.text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test da API (FastAPI + Neo4j)")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    print(f"Testando {args.url}  (prefixo dos dados temporários: {PREFIX}{RUN})")
    try:
        run(args.url)
    except httpx.ConnectError:
        print("\nNão foi possível conectar à API. Ela está rodando? (uvicorn app.main:app --reload)")
        raise SystemExit(2)
    finally:
        try:
            cleanup()
            print("\nDados temporários do teste removidos.")
        except Exception as exc:
            print(f"\nAtenção: não foi possível limpar os dados de teste ({exc}).")
            print(f"Remova manualmente no Neo4j Browser: MATCH (n) WHERE n.name STARTS WITH '{PREFIX}' "
                  f"OR n.title STARTS WITH '{PREFIX}' DETACH DELETE n")

    failed = [d for ok, d in results if not ok]
    print(f"\nResultado: {len(results) - len(failed)}/{len(results)} verificações OK")
    if failed:
        print("Falharam:")
        for d in failed:
            print("  -", d)
        raise SystemExit(1)
    print("\nPARTE 2 VALIDADA: FastAPI -> Python -> Neo4j funcionando.")


if __name__ == "__main__":
    main()
