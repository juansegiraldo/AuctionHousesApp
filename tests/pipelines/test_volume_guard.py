from pipelines.silver.volume_guard import shrunk_houses


def test_silver_igual_o_mayor_que_la_base_pasa():
    assert shrunk_houses({"duran": 100, "morton": 51}, {"duran": 100, "morton": 50}) == []


def test_silver_con_menos_lotes_que_la_base_se_detecta():
    assert shrunk_houses({"duran": 99, "morton": 50}, {"duran": 100, "morton": 50}) == ["duran"]


def test_una_casa_que_desaparece_de_silver_se_detecta():
    assert shrunk_houses({"duran": 100}, {"duran": 100, "zorrilla": 11168}) == ["zorrilla"]


def test_una_casa_aun_no_cargada_en_la_base_no_es_fallo():
    assert shrunk_houses({"duran": 100, "nueva": 5}, {"duran": 100}) == []
