import pytest

from pipelines.shared import attribution_jev


@pytest.fixture(autouse=True)
def _jev_offline(tmp_path, monkeypatch):
    """Ningun test llama a Jev ni toca la cache versionada.

    artist_resolve.main() rellena la cache si encuentra clave, y en la maquina
    del autor la clave existe (../JEV_v0/.env): sin esto la suite gastaria
    dinero y reescribiria pipelines/config/attribution_jev.jsonl.
    """
    monkeypatch.setattr(attribution_jev, "CACHE", tmp_path / "attribution_jev.jsonl")
    monkeypatch.setattr(attribution_jev, "load_api_key", lambda: None)
