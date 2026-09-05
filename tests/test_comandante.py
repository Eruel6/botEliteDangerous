import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import comandante


def _escrever(pasta, conteudo):
    caminho = os.path.join(str(pasta), comandante.NOME_ARQUIVO_CARGO)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(conteudo)
    return str(pasta)


def test_cargo_json_valido_vira_dicionario(tmp_path):
    pasta = _escrever(tmp_path, json.dumps({
        "event": "Cargo",
        "Vessel": "Ship",
        "Count": 740,
        "Inventory": [
            {"Name": "aluminium", "Name_Localised": "Alumínio", "Count": 720, "Stolen": 0},
            {"Name": "steel", "Name_Localised": "Aço", "Count": 20, "Stolen": 0},
        ],
    }))

    assert comandante.ler_cargo_json(pasta) == {"Alumínio": 720, "Aço": 20}


def test_usa_o_nome_cru_quando_nao_ha_localizado(tmp_path):
    pasta = _escrever(tmp_path, json.dumps({"Inventory": [{"Name": "steel", "Count": 20}]}))

    assert comandante.ler_cargo_json(pasta) == {"steel": 20}


def test_arquivo_ausente_devolve_vazio(tmp_path):
    assert comandante.ler_cargo_json(str(tmp_path)) == {}


def test_arquivo_vazio_devolve_vazio(tmp_path):
    assert comandante.ler_cargo_json(_escrever(tmp_path, "")) == {}


def test_arquivo_truncado_no_meio_da_escrita_devolve_vazio(tmp_path):
    """O jogo reescreve esse arquivo enquanto o cliente lê."""
    pasta = _escrever(tmp_path, '{"Inventory": [{"Name": "alumin')

    assert comandante.ler_cargo_json(pasta) == {}


def test_porao_vazio_devolve_vazio(tmp_path):
    pasta = _escrever(tmp_path, json.dumps({"Count": 0, "Inventory": []}))

    assert comandante.ler_cargo_json(pasta) == {}


def test_item_sem_contagem_positiva_e_ignorado(tmp_path):
    pasta = _escrever(tmp_path, json.dumps({
        "Inventory": [
            {"Name_Localised": "Aço", "Count": 0},
            {"Name_Localised": "Ouro", "Count": 5},
        ]
    }))

    assert comandante.ler_cargo_json(pasta) == {"Ouro": 5}
