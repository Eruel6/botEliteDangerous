"""Prova que o parser unificado reproduz o comportamento dos scripts originais.

Os originais (extraídos de HEAD antes do refactor) estão em ``tests/_originais``.
Roda contra os Journals reais quando eles estão presentes.
"""

import glob
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "tests", "_originais"))

import ed_parser as ed
import orig_bot
import orig_parser_materials

JOURNAIS = sorted(glob.glob(os.path.join(RAIZ, "journals", "Journal.*.log")))
requer_journais = pytest.mark.skipif(not JOURNAIS, reason="Journals reais não presentes")


@requer_journais
@pytest.mark.parametrize("log", JOURNAIS, ids=os.path.basename)
def test_mesmas_instalacoes_e_materiais_que_o_bot_original(log):
    antigo = dict(orig_bot.extrair_ultimas_instalacoes(log)[0])
    antigo.pop("Desconhecida", None)

    novo = {
        i.nome: [
            {
                "Name_Localised": m.nome,
                "RequiredAmount": m.requerido,
                "ProvidedAmount": m.fornecido,
            }
            for m in i.materiais
        ]
        for i in ed.extrair_instalacoes(log)
        if i.nome != ed.NOME_DESCONHECIDO
    }

    assert set(novo) == set(antigo)
    for nome in antigo:
        resumo_antigo = [
            (m["Name_Localised"], m["RequiredAmount"], m["ProvidedAmount"]) for m in antigo[nome]
        ]
        resumo_novo = [
            (m["Name_Localised"], m["RequiredAmount"], m["ProvidedAmount"]) for m in novo[nome]
        ]
        assert resumo_novo == resumo_antigo


@requer_journais
@pytest.mark.parametrize("log", JOURNAIS, ids=os.path.basename)
def test_mensagem_do_discord_e_byte_identica_a_original(log):
    for instalacao in ed.extrair_instalacoes(log):
        if instalacao.nome == ed.NOME_DESCONHECIDO:
            continue
        brutos = [
            {
                "Name_Localised": m.nome,
                "RequiredAmount": m.requerido,
                "ProvidedAmount": m.fornecido,
            }
            for m in instalacao.materiais
        ]
        esperado = orig_bot.formatar_mensagem(instalacao.nome, brutos)
        assert ed.formatar_mensagem_discord(instalacao) == esperado


@requer_journais
@pytest.mark.parametrize("log", JOURNAIS, ids=os.path.basename)
def test_tabela_de_terminal_e_identica_a_do_parser_materials(log, capsys):
    materiais, nome = orig_parser_materials.extrair_materiais_construcao(log)
    if not materiais:
        pytest.skip("log sem materiais")
    orig_parser_materials.imprimir_tabela_materiais(materiais, nome)
    esperado = capsys.readouterr().out

    alvo = next(i for i in ed.extrair_instalacoes(log) if i.nome == nome)
    assert ed.formatar_tabela_terminal(alvo) == esperado


@requer_journais
@pytest.mark.parametrize("log", JOURNAIS, ids=os.path.basename)
def test_ultima_instalacao_bate_com_a_do_cliente_original(log):
    import orig_cliente

    nome_antigo, materiais_antigos = orig_cliente.extrair_ultima_instalacao_e_materiais(log)
    nova = ed.ultima_instalacao(log)

    if materiais_antigos is None:
        assert nova is None
        return

    assert nova.nome == nome_antigo
    assert [(m.nome, m.requerido, m.fornecido) for m in nova.materiais] == [
        (m["Name_Localised"], m["RequiredAmount"], m["ProvidedAmount"]) for m in materiais_antigos
    ]
