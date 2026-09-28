# CP3 — Plataforma de Recomendação para Streaming

Neo4j (relacionamentos) + Python + FastAPI (API REST). Redis (cache) entra na **Parte 3**.

**Status:** Parte 1 (Neo4j) ✔ · Parte 2 (Python + FastAPI + Neo4j) ✔ — confirme no seu ambiente com `python tests/smoke_test.py` · Parte 3 (Redis e cache) 

Fluxo desta etapa: `Cliente HTTP → FastAPI → Python → Neo4j`

## Estrutura

```
CP3-STREAMING/
├── docker-compose.yml          # Neo4j 5 (Parte 1)
├── neo4j/
│   ├── constraints.cypher      # unicidade de usuário, filme e gênero (Parte 1)
│   ├── dados.cypher            # 3 usuários, 5 filmes, 4 gêneros e relacionamentos (Parte 1)
│   └── recomendacao.cypher     # consulta de recomendação com $userName (Parte 1)
├── app/
│   ├── main.py                 # cria a API, conecta ao Neo4j, trata erros
│   ├── config.py               # configurações (URI, usuário, senha do Neo4j)
│   ├── database.py             # driver e sessão do Neo4j
│   ├── schemas.py              # modelos de entrada/saída (Pydantic)
│   ├── repository.py           # consultas Cypher
│   ├── errors.py               # erros 404/409
│   └── routers/                # endpoints: users, movies, genres, recommendations
├── tests/
│   ├── test_*.py               # testes automatizados (não precisam do Neo4j)
│   └── smoke_test.py           # teste ponta a ponta contra a API + Neo4j reais
├── requirements.txt
├── pytest.ini
└── .env.example
```

## Como executar localmente

Pré-requisitos: **Docker Desktop** e **Python 3.10+**.

### 1. Subir o Neo4j

```bash
docker compose up -d
```

Neo4j Browser: <http://localhost:7474> — usuário `neo4j`, senha `senha123s`.

Os dados da Parte 1 já devem estar no banco. Para conferir, no Neo4j Browser:

```cypher
MATCH (n) RETURN labels(n)[0] AS tipo, count(n) AS total
```

Esperado: 3 `User`, 5 `Movie`, 4 `Genre`. Se o banco estiver vazio, cole no Neo4j Browser, nesta ordem, o conteúdo de `neo4j/constraints.cypher` e depois `neo4j/dados.cypher`.

> O `docker-compose.yml` não define volume: `docker compose down` remove o container **e os dados**. Para pausar, use `docker compose stop` (e `docker compose start` para retomar).

### 2. Instalar as dependências Python

Na pasta `CP3-STREAMING`:

```bash
python -m venv .venv

# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Iniciar a API

```bash
uvicorn app.main:app --reload
```

- Documentação interativa (Swagger): <http://127.0.0.1:8000/docs>
- Verificação da conexão com o Neo4j: <http://127.0.0.1:8000/health>

Se o Neo4j usar outra URI/senha, copie `.env.example` para `.env` e ajuste.

### 4. Testar

```bash
pytest                      # 37 testes automatizados (sem Neo4j)
python tests/smoke_test.py  # ponta a ponta, com a API e o Neo4j rodando
```

O `smoke_test.py` cria dados com o prefixo `smoke_teste_` e os apaga ao final; os dados da Parte 1 não são alterados.

## Endpoints

| Método | Rota | Descrição | Respostas |
|---|---|---|---|
| POST | `/users` | Cadastrar usuário `{"name": "Marina"}` | 201 · 409 já existe |
| GET | `/users` · `/users/{nome}` | Listar / consultar usuário | 200 · 404 |
| POST | `/genres` | Cadastrar gênero `{"name": "Suspense"}` | 201 · 409 |
| GET | `/genres` | Listar gêneros (com nº de filmes) | 200 |
| POST | `/movies` | Cadastrar filme `{"title": "...", "genres": ["Animação"]}` (gêneros opcionais, devem existir) | 201 · 404 gênero inexistente · 409 |
| GET | `/movies` · `/movies/{título}` | Listar / consultar filme | 200 · 404 |
| POST | `/movies/{título}/genres` | Associar gênero existente `{"genre": "Fantasia"}` | 200 · 404 |
| POST | `/users/{nome}/watched` | Registrar filme assistido `{"movie_title": "Matrix"}` | 201 · 200 já registrado · 404 |
| GET | `/users/{nome}/watched` | Listar filmes assistidos | 200 · 404 |
| POST | `/users/{nome}/ratings` | Avaliar `{"movie_title": "Matrix", "rating": 5}` (1 a 5; só filmes assistidos) | 201 · 200 atualizada · 404 · 409 não assistiu · 422 |
| GET | `/users/{nome}/ratings` | Listar avaliações | 200 · 404 |
| GET | `/users/{nome}/recommendations?limit=10` | **Recomendações personalizadas** | 200 · 404 |
| GET | `/health` | Estado da conexão com o Neo4j | 200 · 503 |

Regras: nomes e títulos têm de 1 a 100 caracteres e não podem conter `/` nem `\`. Repetir um `watched` ou uma avaliação não duplica relacionamentos (a avaliação repetida atualiza a nota).

### Exemplo — recomendação

```bash
curl http://127.0.0.1:8000/users/Julia/recommendations
```

```json
{
  "user": "Julia",
  "total": 1,
  "recommendations": [
    {
      "filme_recomendado": "O Senhor dos Anéis",
      "usuario_referencia": "Carlos",
      "filmes_em_comum": 2,
      "media_notas": 4.5
    }
  ]
}
```

O nome vem da URL e é passado ao parâmetro `$userName` de `neo4j/recomendacao.cypher`, que a API lê diretamente do arquivo (sem cópia). Qualquer usuário cadastrado pode pedir recomendações; usuário inexistente retorna 404. Se o mesmo filme for sugerido por mais de um usuário de referência, aparece uma vez, com a melhor referência.

> No PowerShell, `curl` é um alias de outro comando; use `curl.exe` ou, mais simples, o Swagger em `/docs`.
