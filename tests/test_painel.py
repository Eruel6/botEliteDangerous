# tests/test_painel.py
import json
import os
import sys
import urllib.error
import urllib.request

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import estado
import painel


@pytest.fixture
def servidor_no_ar():
    e = estado.EstadoCliente()
    e.registrar_envio("Obra A", 200)
    servidor, porta = painel.iniciar_painel(e, porta=0)
    yield f"http://127.0.0.1:{porta}", e
    servidor.shutdown()


def buscar(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, r.read().decode("utf-8")


def test_estado_json_devolve_o_estado_do_cliente(servidor_no_ar):
    base, _ = servidor_no_ar

    status, corpo = buscar(f"{base}/estado.json")

    assert status == 200
    assert json.loads(corpo)["ultimo_status_http"] == 200


def test_raiz_devolve_a_pagina(servidor_no_ar):
    base, _ = servidor_no_ar

    status, corpo = buscar(f"{base}/")

    assert status == 200
    assert "<html" in corpo.lower()


def test_nao_serve_o_arquivo_de_config(servidor_no_ar):
    """Regressão de segurança: servir o diretório exporia o token de quem roda."""
    base, _ = servidor_no_ar

    for caminho in ("/config.txt", "/../config.txt", "/painel.py"):
        with pytest.raises(urllib.error.HTTPError) as erro:
            buscar(f"{base}{caminho}")
        assert erro.value.code == 404


def test_liga_apenas_em_localhost(servidor_no_ar):
    _, _ = servidor_no_ar
    servidor, porta = painel.iniciar_painel(estado.EstadoCliente(), porta=0)
    try:
        assert servidor.server_address[0] == "127.0.0.1"
    finally:
        servidor.shutdown()


def test_escolhe_outra_porta_quando_a_pedida_esta_ocupada():
    primeiro, porta = painel.iniciar_painel(estado.EstadoCliente(), porta=0)
    try:
        segundo, outra_porta = painel.iniciar_painel(estado.EstadoCliente(), porta=porta)
        try:
            assert outra_porta != porta
        finally:
            segundo.shutdown()
    finally:
        primeiro.shutdown()
