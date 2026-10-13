import pytest

from pipelines.shared import artist_master, attribution_jev

_REAL_ARTISTS_DIR = artist_master.ARTISTS_DIR


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
