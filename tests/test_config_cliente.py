import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import config_cliente


def escrever(tmp_path, conteudo):
    caminho = tmp_path / "config.txt"
    caminho.write_text(conteudo, encoding="utf-8")
    return str(caminho)


def test_le_token_e_url(tmp_path):
    caminho = escrever(tmp_path, "API_TOKEN=abc123\nAPI_URL=https://exemplo/logdata\n")

    config = config_cliente.carregar_config(caminho)

    assert config.api_token == "abc123"
    assert config.api_url == "https://exemplo/logdata"


def test_ignora_comentarios_e_linhas_vazias(tmp_path):
    caminho = escrever(
        tmp_path,
        "# o token que o Arthur te passou\nAPI_TOKEN=abc123\n\nAPI_URL=https://exemplo/logdata\n",
    )

    assert config_cliente.carregar_config(caminho).api_token == "abc123"


def test_arquivo_ausente_explica_o_que_fazer(tmp_path):
    with pytest.raises(config_cliente.ConfigInvalida) as erro:
        config_cliente.carregar_config(str(tmp_path / "nao-existe.txt"))

    assert "config.exemplo.txt" in str(erro.value)


def test_token_ausente_e_erro(tmp_path):
    caminho = escrever(tmp_path, "API_URL=https://exemplo/logdata\n")

    with pytest.raises(config_cliente.ConfigInvalida) as erro:
        config_cliente.carregar_config(caminho)

    assert "API_TOKEN" in str(erro.value)


def test_token_vazio_e_erro(tmp_path):
    caminho = escrever(tmp_path, "API_TOKEN=\nAPI_URL=https://exemplo/logdata\n")

    with pytest.raises(config_cliente.ConfigInvalida):
        config_cliente.carregar_config(caminho)


def test_url_ausente_e_erro(tmp_path):
    caminho = escrever(tmp_path, "API_TOKEN=abc123\n")

    with pytest.raises(config_cliente.ConfigInvalida) as erro:
        config_cliente.carregar_config(caminho)

    assert "API_URL" in str(erro.value)
