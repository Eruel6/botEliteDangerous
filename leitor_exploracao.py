"""Leitor incremental dos journals para a aba de exploração."""

import glob
import json
import os
import re
import threading
import time

import ed_parser
import precos_vista
from exploracao import Historico

# Mesmo valor de monitor.INTERVALO_CHECAGEM; não importamos monitor para não
# puxar requests/compras para dentro deste módulo.
INTERVALO_PADRAO = 60

_NOME_NOVO = re.compile(r"^Journal\.(\d{4}-\d{2}-\d{2}T\d{6})\.(\d+)\.log$")
_NOME_ANTIGO = re.compile(r"^Journal\.(\d{2})(\d{2})(\d{2})(\d{6})\.(\d+)\.log$")


def ordem_do_journal(caminho: str) -> str:
    """Chave ISO "YYYY-MM-DDTHHMMSS.parte" que ordena os dois formatos de nome."""
    nome = os.path.basename(caminho)
    m = _NOME_NOVO.match(nome)
    if m:
        return f"{m.group(1)}.{int(m.group(2)):02d}"
    m = _NOME_ANTIGO.match(nome)
    if m:
        aa, mm, dd, hora, parte = m.groups()
        return f"20{aa}-{mm}-{dd}T{hora}.{int(parte):02d}"
    return ""


class LeitorExploracao:
    def __init__(self, historico: Historico, pasta: str | None = None):
        self._historico = historico
        self._pasta = os.path.expanduser(pasta or ed_parser.PASTA_JOURNAL_PADRAO)
        self._offsets: dict[str, int] = {}

    def ciclo(self) -> None:
        arquivos = glob.glob(os.path.join(self._pasta, "Journal.*.log"))
        arquivos.sort(key=lambda c: (ordem_do_journal(c), c))
        for caminho in arquivos:
            self._ler(caminho)

    def _ler(self, caminho: str) -> None:
        inicio = self._offsets.get(caminho, 0)
        with open(caminho, "rb") as f:
            f.seek(inicio)
            dados = f.read()
        fim = dados.rfind(b"\n")
        if fim < 0:
            return
        self._offsets[caminho] = inicio + fim + 1
        sessao = os.path.basename(caminho)
        for bruta in dados[: fim + 1].splitlines():
            try:
                evento = json.loads(bruta.decode("utf-8"))
            except ValueError:  # inclui UnicodeDecodeError e JSONDecodeError
                continue
            if isinstance(evento, dict):
                self._historico.consumir(evento, sessao)


def _laco(leitor, historico, estado_cliente, intervalo, dormir=time.sleep) -> None:
    while True:
        try:
            leitor.ciclo()
            estado_cliente.registrar_exploracao(historico.resumo())
        except Exception as e:
            estado_cliente.registrar_erro(f"exploração: {e}")
        dormir(intervalo)


def iniciar_thread(estado_cliente, pasta: str | None = None,
                   intervalo: int = INTERVALO_PADRAO) -> threading.Thread:
    historico = Historico(precos_vista.carregar_precos())
    leitor = LeitorExploracao(historico, pasta)
    t = threading.Thread(target=_laco, args=(leitor, historico, estado_cliente, intervalo),
                         daemon=True, name="exploracao")
    t.start()
    return t
