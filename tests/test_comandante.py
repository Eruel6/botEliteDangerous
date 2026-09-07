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


FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
COM_ENTREGAS = os.path.join(FIXTURES, "journal_com_entregas.log")
SEM_DEPOT = os.path.join(FIXTURES, "journal_sem_depot.log")


def test_extrai_uma_entrega_por_contribuicao():
    assert len(comandante.extrair_entregas(COM_ENTREGAS)) == 3


def test_um_evento_com_duas_contribuicoes_vira_duas_entregas():
    entregas = comandante.extrair_entregas(COM_ENTREGAS)
    do_segundo_evento = [e for e in entregas if e.quando == "2025-05-20T17:40:00Z"]

    assert sorted(e.material for e in do_segundo_evento) == ["Aço", "Ouro"]


def test_a_entrega_carrega_obra_material_e_quantidade():
    (primeira,) = [e for e in comandante.extrair_entregas(COM_ENTREGAS)
                   if e.material == "Alumínio"]

    assert primeira.market_id == 901
    assert primeira.quantidade == 720
    assert primeira.quando == "2025-05-20T17:37:50Z"


def test_log_sem_contribuicao_devolve_lista_vazia():
    assert comandante.extrair_entregas(SEM_DEPOT) == []


def test_o_alvo_e_a_ultima_obra_vista_com_o_sistema_daquele_momento():
    market_id, sistema = comandante.alvo_atual(COM_ENTREGAS)

    assert market_id == 902
    assert sistema == "Outro Sistema"


def test_log_sem_obra_nenhuma_nao_tem_alvo():
    market_id, sistema = comandante.alvo_atual(SEM_DEPOT)

    assert market_id is None
    assert sistema == ""


def test_montar_retrato_junta_porao_alvo_e_entregas(tmp_path):
    pasta = _escrever(tmp_path, json.dumps({
        "Inventory": [{"Name_Localised": "Alumínio", "Count": 720}]
    }))

    retrato = comandante.montar_retrato(COM_ENTREGAS, pasta=pasta)

    assert retrato.carga == {"Alumínio": 720}
    assert retrato.alvo_market_id == 902
    assert retrato.alvo_sistema == "Outro Sistema"
    assert len(retrato.entregas) == 3
