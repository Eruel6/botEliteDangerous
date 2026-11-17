# tests/test_generos_exobio.py
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import generos_exobio
import precos_vista


def test_json_tem_os_21_generos_completos():
    g = generos_exobio.carregar_generos().dados
    assert len(g) == 21
    for nome, info in g.items():
        assert info["descricao"].strip() and info["distancia_m"] > 0
        assert info["fonte_distancia"] in ("wiki", "comunidade")
    assert g["Osseus"]["distancia_m"] == 800 and g["Osseus"]["fonte_distancia"] == "wiki"
    assert g["Electricae"]["distancia_m"] == 1000 and g["Electricae"]["fonte_distancia"] == "comunidade"
    assert g["Bark Mounds"]["wiki"] == "Bark Mound" and g["Crystalline Shards"]["wiki"] == "Crystalline Shard"


def test_todas_as_96_especies_da_tabela_tem_genero():
    g = generos_exobio.carregar_generos()
    sem = [n for n, _ in precos_vista.carregar_precos().lista() if g.genero_de(n) is None]
    assert sem == []


def test_genero_de_casos_de_nome():
    g = generos_exobio.carregar_generos()
    assert g.genero_de("Amphora plant") == "Amphora Plant"
    assert g.genero_de("bacterium  ACIES") == "Bacterium"
    assert g.genero_de("Bark Mounds") == "Bark Mounds"
    assert g.genero_de("Especie Nova") is None
    assert g.genero_de("Bacteriumx Algo") is None
