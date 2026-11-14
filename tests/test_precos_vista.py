# tests/test_precos_vista.py
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import precos_vista


def ler_fixture(nome):
    with open(os.path.join(RAIZ, "tests", "fixtures", nome), encoding="utf-8") as f:
        return f.read()


def test_extrai_todas_as_especies_da_pagina_real():
    precos = precos_vista.extrair_precos_do_html(ler_fixture("vista_genomics.html"))
    assert len(precos) == 96
    assert precos["Bacterium Acies"] == 1_000_000
    assert precos["Fonticulua Fluctus"] == 20_000_000
    assert precos["Stratum Tectonicas"] == 19_010_800


def test_preco_casa_sem_diferenciar_acento_e_caixa():
    p = precos_vista.Precos({"Bacterium Acies": 1_000_000})
    assert p.preco("bacterium  ACIES") == 1_000_000


def test_preco_usa_apelido_para_nome_traduzido():
    p = precos_vista.Precos({"Brain Tree": 1_593_700}, {"Árvore Cerebral": "Brain Tree"})
    assert p.preco("Arvore cerebral") == 1_593_700


def test_especie_desconhecida_devolve_none():
    assert precos_vista.Precos({}).preco("Bacterium Nada") is None


def test_json_versionado_carrega_e_tem_as_96_especies():
    p = precos_vista.carregar_precos()
    assert p.preco("Bacterium Acies") == 1_000_000
    with open(precos_vista.CAMINHO_PADRAO, encoding="utf-8") as f:
        assert len(json.load(f)["especies"]) == 96
