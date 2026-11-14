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
        ({"event": "A"}, "Journal.2025-05-20T141829.01.log"),
        ({"event": "B"}, "Journal.2025-05-20T141829.01.log"),
        ({"event": "C"}, "Journal.2026-11-14T094935.01.log"),
    ]


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
