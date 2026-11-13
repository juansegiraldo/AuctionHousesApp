import pytest

from pipelines.bronze import load_raw
from pipelines.shared import artist_master, attribution_jev

_REAL_ARTISTS_DIR = artist_master.ARTISTS_DIR


@pytest.fixture(autouse=True)
def _supabase_offline(monkeypatch):
    """Ningun test escribe en Supabase: el .env del autor tiene el token real y
    auction.raw_lots es solo de insercion, asi que una fila de prueba no se
    podria borrar nunca. Un test que necesite la red sustituye `_urlopen` el mismo."""
    def _blocked(*args, **kwargs):
        raise AssertionError("un test intento salir a la red hacia Supabase")
    monkeypatch.setattr(load_raw, "_urlopen", _blocked)


@pytest.fixture(autouse=True)
def _jev_offline(tmp_path, monkeypatch):
    """Ningun test llama a Jev ni toca la cache versionada.

    artist_resolve.main() rellena la cache si encuentra clave, y en la maquina
    del autor la clave existe (../JEV_v0/.env): sin esto la suite gastaria
    dinero y reescribiria pipelines/config/attribution_jev.jsonl.
    """
    monkeypatch.setattr(attribution_jev, "CACHE", tmp_path / "attribution_jev.jsonl")
    monkeypatch.setattr(attribution_jev, "load_api_key", lambda: None)
    yield
    # Los tests del maestro REAL ya no vacian la cache (recargar 3.524 artistas
    # en cada caso eran ~170 s de la suite). A cambio, un test que apunte
    # ARTISTS_DIR a un maestro temporal no puede dejarlo cacheado al salir.
    # Corre antes de que monkeypatch restaure ARTISTS_DIR, asi que aun lo ve.
    if artist_master.ARTISTS_DIR != _REAL_ARTISTS_DIR:
        artist_master.reset_caches()
