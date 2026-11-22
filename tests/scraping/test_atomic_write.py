import pytest

from scraping.common.atomic import atomic_write


def test_un_fallo_a_medias_no_deja_fichero_final(tmp_path):
    # El resume da por hecha toda subasta cuyo .jsonl existe: si el scraper muere
    # a mitad, ese fichero no puede existir.
    out = tmp_path / "subasta-1.jsonl"
    with pytest.raises(RuntimeError):
        with atomic_write(out) as fh:
            fh.write(b'{"lot_url": "a"}\n')
            raise RuntimeError("timeout")
    assert not out.exists()
    assert list(tmp_path.glob("*.jsonl")) == []  # el .part no casa con *.jsonl


def test_un_fallo_no_pisa_el_fichero_bueno_anterior(tmp_path):
    out = tmp_path / "historic_all_lots.jsonl"
    out.write_bytes(b"bueno\n")
    with pytest.raises(RuntimeError):
        with atomic_write(out) as fh:
            fh.write(b"a medias")
            raise RuntimeError("corte")
    assert out.read_bytes() == b"bueno\n"


def test_al_terminar_bien_queda_solo_el_fichero_final(tmp_path):
    out = tmp_path / "sub" / "x.jsonl"
    with atomic_write(out) as fh:
        fh.write(b"ok\n")
    assert out.read_bytes() == b"ok\n"
    assert [p.name for p in out.parent.iterdir()] == ["x.jsonl"]
