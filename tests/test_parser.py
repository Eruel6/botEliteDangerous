import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ed_parser as ed

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
BASICO = os.path.join(FIXTURES, "journal_basico.log")


def test_extrai_uma_instalacao_por_market_id():
    instalacoes = ed.extrair_instalacoes(BASICO)
    assert [i.market_id for i in instalacoes] == [4251780355, 4251881219]


def test_resolve_nome_da_instalacao_pelo_market_id():
    a, b = ed.extrair_instalacoes(BASICO)
    assert a.nome == "Planetary Construction Site: Pedder's Forge"
    assert b.nome == "Planetary Construction Site: Montes Biological Enterprise"


def test_nome_e_desconhecida_quando_nao_ha_approach_settlement():
    (inst,) = ed.extrair_instalacoes(os.path.join(FIXTURES, "journal_sem_nome.log"))
    assert inst.nome == "Desconhecida"


def test_mantem_o_estado_mais_recente_de_cada_instalacao():
    a, _ = ed.extrair_instalacoes(BASICO)
    assert a.progresso == 1.0
    assert a.completa is True
    assert a.falhou is False
    assert [m.fornecido for m in a.materiais] == [1677, 124, 165]


def test_material_expõe_nome_localizado_e_quantidade_faltante():
    _, b = ed.extrair_instalacoes(BASICO)
    aco = b.materiais[0]
    assert aco.nome == "Aço"
    assert aco.requerido == 900
    assert aco.fornecido == 90
    assert aco.faltando == 810


def test_porcentagem_usa_soma_de_quantidades():
    _, b = ed.extrair_instalacoes(BASICO)
    assert b.porcentagem == 90 / 1300 * 100


def test_log_sem_depot_nao_retorna_instalacoes():
    assert ed.extrair_instalacoes(os.path.join(FIXTURES, "journal_sem_depot.log")) == []


def test_encontra_o_journal_modificado_mais_recentemente(tmp_path):
    antigo = tmp_path / "Journal.2025-01-01T000000.01.log"
    recente = tmp_path / "Journal.2025-06-01T000000.01.log"
    antigo.write_text("{}\n")
    recente.write_text("{}\n")
    os.utime(antigo, (1, 1))
    os.utime(recente, (2, 2))

    assert ed.encontrar_log_mais_recente(str(tmp_path)) == str(recente)


def test_encontrar_log_devolve_none_quando_pasta_nao_tem_journal(tmp_path):
    (tmp_path / "outra-coisa.txt").write_text("nada")
    assert ed.encontrar_log_mais_recente(str(tmp_path)) is None


def test_mensagem_do_discord_inclui_porcentagem_quando_informada():
    a, _ = ed.extrair_instalacoes(BASICO)
    cabecalho = ed.formatar_mensagem_discord(a, porcentagem="100.0%").splitlines()[0]
    assert cabecalho.endswith("`Planetary Construction Site: Pedder's Forge` `100.0%`")


def test_mensagem_do_discord_e_codificavel_em_utf8():
    a, _ = ed.extrair_instalacoes(BASICO)
    ed.formatar_mensagem_discord(a).encode("utf-8")


def test_instalacao_a_partir_do_payload_da_api():
    inst = ed.instalacao_de_payload(
        "Planetary Construction Site: X",
        [{"Name_Localised": "Aço", "RequiredAmount": 10, "ProvidedAmount": 4}],
    )
    assert inst.nome == "Planetary Construction Site: X"
    assert inst.materiais[0].faltando == 6
    assert inst.porcentagem == 40.0


def test_ultima_instalacao_e_a_atualizada_por_ultimo_no_log():
    # No fixture, o último ColonisationConstructionDepot é o da instalação A.
    assert ed.ultima_instalacao(BASICO).market_id == 4251780355


def test_ultima_instalacao_e_none_em_log_sem_depot():
    assert ed.ultima_instalacao(os.path.join(FIXTURES, "journal_sem_depot.log")) is None


def test_sinais_de_construcao_lista_os_sites_anunciados_no_log():
    assert ed.sinais_de_construcao(BASICO) == {
        "Planetary Construction Site: Pedder's Forge",
        "Planetary Construction Site: Montes Biological Enterprise",
    }


def test_sinais_de_construcao_ignora_sinais_de_outros_tipos():
    assert ed.sinais_de_construcao(os.path.join(FIXTURES, "journal_sem_depot.log")) == set()


def test_le_de_volta_o_nome_da_instalacao_a_partir_da_mensagem_postada():
    a, _ = ed.extrair_instalacoes(BASICO)
    conteudo = ed.formatar_mensagem_discord(a, porcentagem="97.5%")

    assert ed.nome_na_mensagem(conteudo) == "Planetary Construction Site: Pedder's Forge"


def test_le_de_volta_o_nome_em_mensagem_sem_porcentagem():
    a, _ = ed.extrair_instalacoes(BASICO)

    assert ed.nome_na_mensagem(ed.formatar_mensagem_discord(a)) == a.nome


def test_nome_na_mensagem_devolve_none_para_texto_alheio():
    assert ed.nome_na_mensagem("oi pessoal, alguem vai pra Colonia hoje?") is None


def test_le_de_volta_os_materiais_a_partir_da_mensagem_postada():
    a, _ = ed.extrair_instalacoes(BASICO)
    conteudo = ed.formatar_mensagem_discord(a, porcentagem="100.0%")

    lidos = ed.materiais_na_mensagem(conteudo)

    assert [(m.nome, m.requerido, m.fornecido) for m in lidos] == [
        (m.nome, m.requerido, m.fornecido) for m in a.materiais
    ]


def test_le_de_volta_materiais_com_nome_maior_que_a_coluna():
    inst = ed.instalacao_de_payload(
        "X",
        [{"Name_Localised": "Fabricantes de construções pesadas", "RequiredAmount": 165, "ProvidedAmount": 3}],
    )
    (lido,) = ed.materiais_na_mensagem(ed.formatar_mensagem_discord(inst))

    assert (lido.nome, lido.requerido, lido.fornecido) == ("Fabricantes de construções pesadas", 165, 3)


def test_materiais_na_mensagem_devolve_vazio_para_texto_alheio():
    assert ed.materiais_na_mensagem("papo do canal") == []
