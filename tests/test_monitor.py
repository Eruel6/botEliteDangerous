import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import config_cliente
import ed_parser
import estado
import monitor

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
BASICO = os.path.join(FIXTURES, "journal_basico.log")

CONFIG = config_cliente.Config(api_token="tok", api_url="https://exemplo/logdata")


def test_payload_inclui_o_market_id():
    (inst, _) = ed_parser.extrair_instalacoes(BASICO)

    payload = monitor.payload_de(inst)

    assert payload["market_id"] == 4251780355
    assert payload["instalacao"] == "Planetary Construction Site: Pedder's Forge"


def test_envio_que_falha_e_reenviado_no_ciclo_seguinte():
    tentativas = []

    def enviar_falhando(payload, config):
        tentativas.append(payload["instalacao"])
        return 500

    memoria = {}
    e = estado.EstadoCliente()
    monitor.sincronizar(BASICO, memoria, CONFIG, e, enviar=enviar_falhando)
    quantas_na_primeira = len(tentativas)

    monitor.sincronizar(BASICO, memoria, CONFIG, e, enviar=enviar_falhando)

    assert len(tentativas) == quantas_na_primeira * 2, "deveria ter reenviado tudo"


def test_envio_bem_sucedido_nao_e_reenviado():
    tentativas = []

    def enviar_ok(payload, config):
        tentativas.append(payload["instalacao"])
        return 200

    memoria = {}
    e = estado.EstadoCliente()
    monitor.sincronizar(BASICO, memoria, CONFIG, e, enviar=enviar_ok)
    quantas = len(tentativas)

    monitor.sincronizar(BASICO, memoria, CONFIG, e, enviar=enviar_ok)

    assert len(tentativas) == quantas, "não deveria ter reenviado nada"


def test_relato_ignorado_pelo_servidor_conta_como_sucesso():
    """200 com status 'ignorado' significa que o servidor recebeu e decidiu.
    Reenviar seria um loop inútil."""
    tentativas = []

    def enviar_ignorado(payload, config):
        tentativas.append(payload["instalacao"])
        return 200

    memoria = {}
    e = estado.EstadoCliente()
    monitor.sincronizar(BASICO, memoria, CONFIG, e, enviar=enviar_ignorado)
    quantas = len(tentativas)

    monitor.sincronizar(BASICO, memoria, CONFIG, e, enviar=enviar_ignorado)

    assert len(tentativas) == quantas


def test_registra_a_leitura_no_estado():
    e = estado.EstadoCliente()

    monitor.sincronizar(BASICO, {}, CONFIG, e, enviar=lambda p, c: 200)

    d = e.como_dicionario()
    assert d["journal_atual"] == BASICO
    assert len(d["instalacoes"]) == 2


def test_registra_erro_no_estado_quando_o_envio_falha():
    e = estado.EstadoCliente()

    monitor.sincronizar(BASICO, {}, CONFIG, e, enviar=lambda p, c: 401)

    erros = e.como_dicionario()["erros"]
    assert erros, "um 401 deveria virar erro visível"
    assert "401" in erros[0]["mensagem"]


def test_ignora_instalacao_desconhecida():
    enviados = []
    monitor.sincronizar(
        os.path.join(FIXTURES, "journal_sem_fonte_de_nome.log"),
        {},
        CONFIG,
        estado.EstadoCliente(),
        enviar=lambda p, c: enviados.append(p) or 200,
    )

    assert enviados == []


def test_manda_o_token_e_a_url_da_config(monkeypatch):
    capturado = {}

    def post_falso(url, json=None, headers=None, timeout=None):
        capturado["url"] = url
        capturado["headers"] = headers

        class R:
            status_code = 200
            text = "ok"

        return R()

    monkeypatch.setattr(monitor.requests, "post", post_falso)

    monitor.enviar_para_api({"instalacao": "X"}, CONFIG)

    assert capturado["url"] == "https://exemplo/logdata"
    assert capturado["headers"]["X-API-Token"] == "tok"


def test_falha_de_rede_devolve_none(monkeypatch):
    def post_explodindo(*args, **kwargs):
        raise OSError("rede caiu")

    monkeypatch.setattr(monitor.requests, "post", post_explodindo)

    assert monitor.enviar_para_api({"instalacao": "X"}, CONFIG) is None
