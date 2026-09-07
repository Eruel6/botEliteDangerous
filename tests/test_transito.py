import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import ed_parser
import transito


def _obra(market_id, sistema, faltas):
    """faltas: {material: quanto falta}"""
    return ed_parser.Instalacao(
        market_id=market_id,
        nome=f"Obra {market_id}",
        materiais=[
            ed_parser.Material(nome=m, nome_interno="", requerido=q, fornecido=0)
            for m, q in faltas.items()
        ],
        sistema=sistema,
    )


def test_tudo_cabe_no_alvo():
    obras = [_obra(1, "Sol", {"Aço": 500})]

    assert transito.atribuir({"Aço": 300}, obras, 1, "Sol") == {1: {"Aço": 300}}


def test_o_teto_do_alvo_e_respeitado():
    obras = [_obra(1, "Sol", {"Aço": 100})]

    assert transito.atribuir({"Aço": 300}, obras, 1, "Sol") == {1: {"Aço": 100}}


def test_o_excedente_transborda_para_a_que_mais_precisa():
    obras = [
        _obra(1, "Sol", {"Aço": 100}),
        _obra(2, "Sol", {"Aço": 50}),
        _obra(3, "Sol", {"Aço": 400}),
    ]

    assert transito.atribuir({"Aço": 300}, obras, 1, "Sol") == {1: {"Aço": 100}, 3: {"Aço": 200}}


def test_o_transbordo_continua_na_proxima_quando_a_primeira_enche():
    obras = [
        _obra(1, "Sol", {"Aço": 100}),
        _obra(2, "Sol", {"Aço": 50}),
        _obra(3, "Sol", {"Aço": 120}),
    ]

    resultado = transito.atribuir({"Aço": 300}, obras, 1, "Sol")

    assert resultado == {1: {"Aço": 100}, 3: {"Aço": 120}, 2: {"Aço": 50}}


def test_o_que_nao_cabe_em_lugar_nenhum_e_descartado():
    obras = [_obra(1, "Sol", {"Aço": 100})]

    assert transito.atribuir({"Aço": 900}, obras, 1, "Sol") == {1: {"Aço": 100}}


def test_obra_de_outro_sistema_nao_recebe_transbordo():
    obras = [_obra(1, "Sol", {"Aço": 100}), _obra(2, "Outro", {"Aço": 500})]

    assert transito.atribuir({"Aço": 300}, obras, 1, "Sol") == {1: {"Aço": 100}}


def test_obra_sem_sistema_nao_recebe_transbordo():
    """Linha vinda da reconciliação do canal: a mensagem não carrega o sistema."""
    obras = [_obra(1, "Sol", {"Aço": 100}), _obra(2, "", {"Aço": 500})]

    assert transito.atribuir({"Aço": 300}, obras, 1, "Sol") == {1: {"Aço": 100}}


def test_material_que_ninguem_precisa_e_ignorado():
    obras = [_obra(1, "Sol", {"Aço": 100})]

    assert transito.atribuir({"Ouro": 50}, obras, 1, "Sol") == {}


def test_sem_alvo_vai_direto_para_o_transbordo():
    obras = [_obra(1, "Sol", {"Aço": 100}), _obra(2, "Sol", {"Aço": 400})]

    assert transito.atribuir({"Aço": 300}, obras, None, "Sol") == {2: {"Aço": 300}}


def test_alvo_ja_completo_transborda_tudo():
    obras = [_obra(1, "Sol", {}), _obra(2, "Sol", {"Aço": 400})]

    assert transito.atribuir({"Aço": 300}, obras, 1, "Sol") == {2: {"Aço": 300}}


def test_obra_sem_market_id_nao_participa():
    """Duas linhas reconciliadas teriam market_id None e colidiriam na chave."""
    obras = [_obra(None, "Sol", {"Aço": 100}), _obra(1, "Sol", {"Aço": 100})]

    assert transito.atribuir({"Aço": 300}, obras, 1, "Sol") == {1: {"Aço": 100}}
