import json
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import estado
import leitor_exploracao


class HistoricoFalso:
    def __init__(self):
        self.chamadas = []

    def consumir(self, evento, sessao):
        self.chamadas.append((evento, sessao))

    def resumo(self):
        return {"n": len(self.chamadas)}


class Parar(Exception):
    pass


def dormir_ate(vezes):
    contagem = []

    def dormir(_):
        contagem.append(1)
        if len(contagem) >= vezes:
            raise Parar

    return dormir, contagem


def linha(**kw):
    return json.dumps(kw) + "\n"


def escrever(pasta, nome, texto):
    with open(os.path.join(str(pasta), nome), "a", encoding="utf-8") as f:
        f.write(texto)


def test_ordena_formatos_antigo_e_novo_cronologicamente():
    nomes = ["Journal.2026-11-14T094935.01.log", "Journal.210512183022.01.log",
             "Journal.2025-05-20T141829.01.log", "Journal.210512183022.02.log"]
    assert sorted(nomes, key=leitor_exploracao.ordem_do_journal) == [
        "Journal.210512183022.01.log", "Journal.210512183022.02.log",
        "Journal.2025-05-20T141829.01.log", "Journal.2026-11-14T094935.01.log"]


def test_nome_fora_do_padrao_vai_para_o_comeco():
    assert leitor_exploracao.ordem_do_journal("Journal.estranho.log") == ""


def test_ciclo_consome_eventos_de_varios_arquivos_em_ordem(tmp_path):
    escrever(tmp_path, "Journal.2026-11-14T094935.01.log", linha(event="C"))
    escrever(tmp_path, "Journal.2025-05-20T141829.01.log", linha(event="A") + linha(event="B"))
    h = HistoricoFalso()
    leitor_exploracao.LeitorExploracao(h, str(tmp_path)).ciclo()
    assert h.chamadas == [
        ({"event": "A"}, "Journal.2025-05-20T141829"),
        ({"event": "B"}, "Journal.2025-05-20T141829"),
        ({"event": "C"}, "Journal.2026-11-14T094935"),
    ]


def test_partes_do_mesmo_journal_sao_a_mesma_sessao(tmp_path):
    escrever(tmp_path, "Journal.2026-11-14T094935.01.log", linha(event="A"))
    escrever(tmp_path, "Journal.2026-11-14T094935.02.log", linha(event="B"))
    escrever(tmp_path, "Journal.210512183022.01.log", linha(event="C"))
    h = HistoricoFalso()
    leitor_exploracao.LeitorExploracao(h, str(tmp_path)).ciclo()
    assert [s for _, s in h.chamadas] == [
        "Journal.210512183022", "Journal.2026-11-14T094935", "Journal.2026-11-14T094935"]


def test_arquivo_ilegivel_no_meio_nao_impede_os_outros(tmp_path, monkeypatch):
    for nome, ev in (("Journal.2026-11-14T090000.01.log", "A"),
                     ("Journal.2026-11-14T100000.01.log", "X"),
                     ("Journal.2026-11-14T110000.01.log", "C")):
        escrever(tmp_path, nome, linha(event=ev))
    abrir = open

    def abrir_falhando(caminho, *a, **kw):
        if "T100000" in str(caminho):
            raise PermissionError("acesso negado")
        return abrir(caminho, *a, **kw)

    monkeypatch.setattr("builtins.open", abrir_falhando)
    h = HistoricoFalso()
    erros = leitor_exploracao.LeitorExploracao(h, str(tmp_path)).ciclo()
    assert [c[0]["event"] for c in h.chamadas] == ["A", "C"]
    assert erros == ["Journal.2026-11-14T100000.01.log: acesso negado"]


def test_erro_num_evento_nao_perde_os_seguintes_do_mesmo_bloco(tmp_path):
    escrever(tmp_path, "Journal.2026-11-14T094935.01.log",
             linha(event="A") + linha(event="Quebra") + linha(event="B"))

    class Historico(HistoricoFalso):
        def consumir(self, evento, sessao):
            if evento["event"] == "Quebra":
                raise KeyError("BodyID")
            super().consumir(evento, sessao)

    h = Historico()
    erros = leitor_exploracao.LeitorExploracao(h, str(tmp_path)).ciclo()
    assert [c[0]["event"] for c in h.chamadas] == ["A", "B"]
    assert erros == ["evento Quebra: 'BodyID'"]


def test_arquivo_sem_bytes_novos_nao_e_aberto(tmp_path, monkeypatch):
    escrever(tmp_path, "Journal.2026-11-14T094935.01.log", linha(event="A"))
    h = HistoricoFalso()
    leitor = leitor_exploracao.LeitorExploracao(h, str(tmp_path))
    leitor.ciclo()

    def proibido(*a, **kw):
        raise AssertionError("não devia abrir")

    monkeypatch.setattr("builtins.open", proibido)
    assert leitor.ciclo() == []
    assert len(h.chamadas) == 1


def test_segundo_ciclo_so_le_linhas_novas(tmp_path):
    nome = "Journal.2026-11-14T094935.01.log"
    escrever(tmp_path, nome, linha(event="A"))
    h = HistoricoFalso()
    leitor = leitor_exploracao.LeitorExploracao(h, str(tmp_path))
    leitor.ciclo()
    escrever(tmp_path, nome, linha(event="B"))
    leitor.ciclo()
    assert [c[0]["event"] for c in h.chamadas] == ["A", "B"]


def test_linha_incompleta_no_fim_fica_para_o_proximo_ciclo(tmp_path):
    nome = "Journal.2026-11-14T094935.01.log"
    escrever(tmp_path, nome, linha(event="A") + '{"event":"Scan"')
    h = HistoricoFalso()
    leitor = leitor_exploracao.LeitorExploracao(h, str(tmp_path))
    leitor.ciclo()
    assert [c[0]["event"] for c in h.chamadas] == ["A"]
    escrever(tmp_path, nome, "}\n")
    leitor.ciclo()
    assert [c[0]["event"] for c in h.chamadas] == ["A", "Scan"]
    leitor.ciclo()
    assert len(h.chamadas) == 2


def test_linha_invalida_e_pulada(tmp_path):
    caminho = os.path.join(str(tmp_path), "Journal.2026-11-14T094935.01.log")
    with open(caminho, "wb") as f:
        f.write(linha(event="A").encode() + b"isso nao e json\n" + b"\xff\xfe\n"
                + linha(event="B").encode())
    h = HistoricoFalso()
    leitor_exploracao.LeitorExploracao(h, str(tmp_path)).ciclo()
    assert [c[0]["event"] for c in h.chamadas] == ["A", "B"]


def test_pasta_vazia_nao_falha(tmp_path):
    h = HistoricoFalso()
    leitor_exploracao.LeitorExploracao(h, str(tmp_path)).ciclo()
    assert h.chamadas == []


def test_pasta_inexistente_nao_falha(tmp_path):
    h = HistoricoFalso()
    leitor_exploracao.LeitorExploracao(h, str(tmp_path / "nao_existe")).ciclo()
    assert h.chamadas == []


def test_laco_registra_o_resumo_a_cada_ciclo(tmp_path):
    e = estado.EstadoCliente()
    h = HistoricoFalso()
    escrever(tmp_path, "Journal.2026-11-14T094935.01.log", linha(event="A"))
    dormir, contagem = dormir_ate(2)
    with pytest.raises(Parar):
        leitor_exploracao._laco(leitor_exploracao.LeitorExploracao(h, str(tmp_path)), h, e, 1, dormir)
    assert len(contagem) == 2
    assert e.exploracao() == {"carregando": False, "n": 1}


def test_laco_registra_erro_do_ciclo_e_segue():
    e = estado.EstadoCliente()

    class Quebrado:
        def ciclo(self):
            raise RuntimeError("falhou")

    dormir, contagem = dormir_ate(2)
    with pytest.raises(Parar):
        leitor_exploracao._laco(Quebrado(), HistoricoFalso(), e, 1, dormir)
    assert len(contagem) == 2
    assert e.como_dicionario()["erros"][0]["mensagem"] == "exploração: falhou"


def test_laco_publica_o_resumo_mesmo_com_erros_e_registra_cada_erro_uma_vez():
    e = estado.EstadoCliente()
    h = HistoricoFalso()

    class ComErros:
        def ciclo(self):
            h.consumir({"event": "A"}, "s")
            return ["Journal.x.log: acesso negado"]

    dormir, _ = dormir_ate(3)
    with pytest.raises(Parar):
        leitor_exploracao._laco(ComErros(), h, e, 1, dormir)
    assert e.exploracao() == {"carregando": False, "n": 3}
    assert [x["mensagem"] for x in e.como_dicionario()["erros"]] == [
        "exploração: Journal.x.log: acesso negado"]


def test_laco_nao_repete_o_mesmo_erro_de_ciclo():
    e = estado.EstadoCliente()

    class Quebrado:
        def ciclo(self):
            raise RuntimeError("falhou")

    dormir, _ = dormir_ate(3)
    with pytest.raises(Parar):
        leitor_exploracao._laco(Quebrado(), HistoricoFalso(), e, 1, dormir)
    assert len(e.como_dicionario()["erros"]) == 1


def test_iniciar_thread_sem_fichas_dos_generos_registra_erro_e_segue(monkeypatch, tmp_path):
    def falha(*a, **k):
        raise FileNotFoundError("generos_exobio.json")

    monkeypatch.setattr(leitor_exploracao.generos_exobio, "carregar_generos", falha)
    e = estado.EstadoCliente()
    t = leitor_exploracao.iniciar_thread(e, str(tmp_path), intervalo=3600)
    assert t.is_alive()
    mensagens = [x["mensagem"] for x in e.como_dicionario()["erros"]]
    assert any("fichas dos gêneros indisponíveis" in m for m in mensagens)
