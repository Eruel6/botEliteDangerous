"""Ponto de entrada: config inválida tem que aparecer no terminal e no painel."""

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import cliente
import config_cliente


def test_config_invalida_sobe_o_painel_registra_o_erro_e_devolve_1(monkeypatch, capsys):
    """Spec: sem config.txt, ou sem token, o cliente não entra no loop: diz o
    que falta no terminal e no painel, e para. Antes da correção, main()
    devolvia 1 antes de subir o painel — a mensagem só existia no terminal."""
    chamadas = {}

    def iniciar_painel_falso(estado_cliente, **kwargs):
        chamadas["estado"] = estado_cliente
        return ("servidor-falso", 9999)

    monkeypatch.setattr(cliente.painel, "iniciar_painel", iniciar_painel_falso)

    def carregar_falhando(caminho="config.txt"):
        raise config_cliente.ConfigInvalida("Faltou preencher em config.txt: API_TOKEN.")

    monkeypatch.setattr(cliente.config_cliente, "carregar_config", carregar_falhando)

    def interromper():
        raise KeyboardInterrupt

    codigo = cliente.main(aguardar=interromper)

    saida = capsys.readouterr().out
    assert codigo == 1
    assert "estado" in chamadas, "o painel deveria ter sido erguido mesmo com config inválida"
    assert "API_TOKEN" in saida, "a mensagem de erro tem que aparecer no terminal"
    assert "http://127.0.0.1:9999" in saida, "a URL do painel tem que aparecer no terminal"

    erros = chamadas["estado"].como_dicionario()["erros"]
    assert erros, "o erro tem que estar registrado no EstadoCliente para o painel mostrar"
    assert "API_TOKEN" in erros[0]["mensagem"]


def test_config_invalida_mantem_o_processo_vivo_ate_interromper(monkeypatch):
    """O processo não pode sair sozinho — só quando a pessoa fecha a janela."""
    monkeypatch.setattr(
        cliente.painel, "iniciar_painel", lambda estado_cliente, **kw: ("srv", 8765)
    )

    def carregar_falhando(caminho="config.txt"):
        raise config_cliente.ConfigInvalida("Não encontrei config.txt.")

    monkeypatch.setattr(cliente.config_cliente, "carregar_config", carregar_falhando)

    chamou = {"vezes": 0}

    def aguardar_fake():
        chamou["vezes"] += 1
        raise KeyboardInterrupt

    codigo = cliente.main(aguardar=aguardar_fake)

    assert chamou["vezes"] == 1, "main() precisa aguardar até KeyboardInterrupt"
    assert codigo == 1


def test_config_valida_sobe_o_painel_e_roda_o_monitor(monkeypatch):
    """Regressão: o caminho feliz continua igual depois da correção."""
    monkeypatch.setattr(
        cliente.painel, "iniciar_painel", lambda estado_cliente, **kw: ("srv", 8765)
    )
    monkeypatch.setattr(cliente.webbrowser, "open", lambda url: None)

    config_falsa = config_cliente.Config(api_token="tok", api_url="https://x/logdata")
    monkeypatch.setattr(cliente.config_cliente, "carregar_config", lambda: config_falsa)

    chamado = {}

    def rodar_falso(config, estado_cliente):
        chamado["config"] = config
        raise KeyboardInterrupt

    monkeypatch.setattr(cliente.monitor, "rodar", rodar_falso)

    codigo = cliente.main()

    assert codigo == 0
    assert chamado["config"] is config_falsa
