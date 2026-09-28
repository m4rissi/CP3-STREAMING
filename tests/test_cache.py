"""Testes da camada de cache (Parte 3).

Não dependem de um Redis real: usam um cliente falso em memória que imita
os comandos usados pela aplicação (get, setex, ttl, ping). Os testes contra
o Redis real ficam no tests/smoke_test.py.
"""
import json

import pytest
import redis

from app import cache
from app.config import get_settings


class FakeRedis:
    """Redis em memória, com TTL registrado por chave."""

    def __init__(self, quebrado: bool = False):
        self.dados: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.quebrado = quebrado

    def _checa(self):
        if self.quebrado:
            raise redis.ConnectionError("Redis indisponível (simulado).")

    def get(self, key):
        self._checa()
        return self.dados.get(key)

    def setex(self, key, ttl, value):
        self._checa()
        self.dados[key] = value
        self.ttls[key] = ttl
        return True

    def ttl(self, key):
        self._checa()
        return self.ttls.get(key, -2)

    def ping(self):
        self._checa()
        return True

    def scan_iter(self, match=None, count=None):
        self._checa()
        import fnmatch
        return [k for k in list(self.dados) if match is None or fnmatch.fnmatch(k, match)]

    def delete(self, *keys):
        self._checa()
        removidas = 0
        for k in keys:
            if self.dados.pop(k, None) is not None:
                self.ttls.pop(k, None)
                removidas += 1
        return removidas

    def info(self):
        self._checa()
        return {"keyspace_hits": 8, "keyspace_misses": 2,
                "used_memory_human": "1.00M", "connected_clients": 1}


@pytest.fixture
def redis_falso(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "_client", fake)
    return fake


# ---------- chave ----------
def test_chave_inclui_usuario_e_limite():
    assert cache.build_key("Julia", 10) == "rec:Julia:10"
    # Limites diferentes geram chaves diferentes: são resultados diferentes.
    assert cache.build_key("Julia", 3) != cache.build_key("Julia", 10)


# ---------- MISS e HIT ----------
def test_primeira_leitura_e_miss_e_a_segunda_e_hit(redis_falso):
    chave = cache.build_key("Julia", 10)
    itens = [{"filme_recomendado": "O Senhor dos Anéis"}]

    estado, conteudo, ttl = cache.read(chave)
    assert estado == "MISS" and conteudo is None

    cache.write(chave, itens)

    estado, conteudo, ttl = cache.read(chave)
    assert estado == "HIT"
    assert conteudo == itens
    assert ttl == get_settings().cache_ttl_seconds


# ---------- TTL ----------
def test_gravacao_sempre_define_ttl(redis_falso):
    chave = cache.build_key("Carlos", 10)
    ttl_aplicado = cache.write(chave, [])

    assert ttl_aplicado == get_settings().cache_ttl_seconds
    # A chave nunca fica no Redis sem prazo de validade.
    assert redis_falso.ttls[chave] > 0


def test_conteudo_gravado_e_json_legivel(redis_falso):
    chave = cache.build_key("Julia", 10)
    cache.write(chave, [{"filme_recomendado": "O Senhor dos Anéis"}])

    gravado = json.loads(redis_falso.dados[chave])
    assert gravado[0]["filme_recomendado"] == "O Senhor dos Anéis"


# ---------- falhas e desligamento ----------
def test_redis_fora_do_ar_devolve_down(monkeypatch):
    monkeypatch.setattr(cache, "_client", FakeRedis(quebrado=True))
    estado, conteudo, ttl = cache.read(cache.build_key("Julia", 10))
    assert estado == "DOWN" and conteudo is None


def test_sem_cliente_devolve_down(monkeypatch):
    monkeypatch.setattr(cache, "_client", None)
    assert cache.read("rec:Julia:10")[0] == "DOWN"
    assert cache.write("rec:Julia:10", []) is None


def test_cache_desligado_por_configuracao(monkeypatch, redis_falso):
    monkeypatch.setattr(get_settings(), "cache_enabled", False)
    assert cache.read(cache.build_key("Julia", 10))[0] == "DISABLED"
    assert cache.get_client() is None


def test_ping_nunca_lanca_excecao(monkeypatch):
    monkeypatch.setattr(cache, "_client", FakeRedis(quebrado=True))
    assert cache.ping() is False


# ---------- invalidação ----------
def test_invalidar_usuario_remove_todas_as_suas_chaves(redis_falso):
    cache.write(cache.build_key("Julia", 10), [])
    cache.write(cache.build_key("Julia", 3), [])
    cache.write(cache.build_key("Carlos", 10), [])

    removidas = cache.invalidate_user("Julia")

    assert removidas == 2
    # O cache dos outros usuários não é afetado.
    assert cache.read(cache.build_key("Carlos", 10))[0] == "HIT"
    assert cache.read(cache.build_key("Julia", 10))[0] == "MISS"


def test_invalidar_usuario_sem_cache_nao_falha(redis_falso):
    assert cache.invalidate_user("Ana") == 0


def test_invalidar_tudo_remove_apenas_as_chaves_da_aplicacao(redis_falso):
    cache.write(cache.build_key("Julia", 10), [])
    cache.write(cache.build_key("Carlos", 10), [])
    redis_falso.dados["outro_sistema:dado"] = "valor"

    removidas = cache.invalidate_all()

    assert removidas == 2
    # Chaves de fora do prefixo rec: continuam intactas.
    assert "outro_sistema:dado" in redis_falso.dados


def test_invalidacao_com_redis_fora_do_ar_devolve_zero(monkeypatch):
    monkeypatch.setattr(cache, "_client", FakeRedis(quebrado=True))
    assert cache.invalidate_user("Julia") == 0
    assert cache.invalidate_all() == 0


# ---------- ciclo completo ----------
def test_ciclo_hit_invalidacao_miss(redis_falso):
    """Julia tem recomendação salva, avalia um filme, e a próxima consulta é MISS."""
    chave = cache.build_key("Julia", 10)
    cache.write(chave, [{"filme_recomendado": "O Senhor dos Anéis"}])
    assert cache.read(chave)[0] == "HIT"

    cache.invalidate_user("Julia")  # o que acontece ao assistir ou avaliar

    assert cache.read(chave)[0] == "MISS"


# ---------- estatísticas ----------
def test_stats_lista_as_chaves_guardadas(redis_falso):
    cache.write(cache.build_key("Julia", 10), [])
    info = cache.stats()

    assert info["redis"] == "connected"
    assert info["cached_recommendations"] == 1
    assert info["keys"] == ["rec:Julia:10"]
    assert info["ttl_seconds"] == get_settings().cache_ttl_seconds
