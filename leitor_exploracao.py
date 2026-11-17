"""Leitor incremental dos journals para a aba de exploração."""

import glob
import json
import os
import re
import threading
import time

import ed_parser
import generos_exobio
import precos_vista
from exploracao import Historico

# Mesmo valor de monitor.INTERVALO_CHECAGEM; não importamos monitor para não
# puxar requests/compras para dentro deste módulo.
INTERVALO_PADRAO = 60

_NOME_NOVO = re.compile(r"^Journal\.(\d{4}-\d{2}-\d{2}T\d{6})\.(\d+)\.log$")
_NOME_ANTIGO = re.compile(r"^Journal\.(\d{2})(\d{2})(\d{2})(\d{6})\.(\d+)\.log$")
_PARTE = re.compile(r"\.\d+\.log$")


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


def sessao_do_journal(caminho: str) -> str:
    """Nome do journal sem a parte ".NN.log": as partes .01, .02 são uma sessão só."""
    return _PARTE.sub("", os.path.basename(caminho))


class LeitorExploracao:
    def __init__(self, historico: Historico, pasta: str | None = None):
        self._historico = historico
        self._pasta = os.path.expanduser(pasta or ed_parser.PASTA_JOURNAL_PADRAO)
        self._offsets: dict[str, int] = {}

    def ciclo(self) -> list[str]:
        """Lê o que há de novo; devolve as mensagens de erro do ciclo.

        Um arquivo ilegível ou um evento que quebra não impede o resto."""
        erros: list[str] = []
        arquivos = glob.glob(os.path.join(self._pasta, "Journal.*.log"))
        arquivos.sort(key=lambda c: (ordem_do_journal(c), c))
        for caminho in arquivos:
            try:
                self._ler(caminho, erros)
            except Exception as e:
                erros.append(f"{os.path.basename(caminho)}: {e}")
        return erros

    def _ler(self, caminho: str, erros: list[str]) -> None:
        inicio = self._offsets.get(caminho, 0)
        if os.path.getsize(caminho) == inicio:
            return
        with open(caminho, "rb") as f:
            f.seek(inicio)
            dados = f.read()
        fim = dados.rfind(b"\n")
        if fim < 0:
            return
        self._offsets[caminho] = inicio + fim + 1
        sessao = sessao_do_journal(caminho)
        for bruta in dados[: fim + 1].splitlines():
            try:
                evento = json.loads(bruta.decode("utf-8"))
            except ValueError:  # inclui UnicodeDecodeError e JSONDecodeError
                continue
            if not isinstance(evento, dict):
                continue
            try:
                self._historico.consumir(evento, sessao)
            except Exception as e:
                erros.append(f"evento {evento.get('event')}: {e}")


def _laco(leitor, historico, estado_cliente, intervalo, dormir=time.sleep) -> None:
    # Cada mensagem distinta vai uma vez só para "Erros recentes": repetir a cada
    # ciclo empurraria para fora os erros da colonização.
    ja_reportados: set[str] = set()
    while True:
        try:
            erros = list(leitor.ciclo() or [])
        except Exception as e:
            erros = [str(e)]
        try:
            estado_cliente.registrar_exploracao(historico.resumo())
        except Exception as e:
            erros.append(str(e))
        for mensagem in erros:
            if mensagem not in ja_reportados:
                ja_reportados.add(mensagem)
                estado_cliente.registrar_erro(f"exploração: {mensagem}")
        dormir(intervalo)


def iniciar_thread(estado_cliente, pasta: str | None = None,
                   intervalo: int = INTERVALO_PADRAO) -> threading.Thread:
    try:
        generos = generos_exobio.carregar_generos()
    except (OSError, ValueError, KeyError) as e:
        estado_cliente.registrar_erro(f"exploração: fichas dos gêneros indisponíveis: {e}")
        generos = None
    historico = Historico(precos_vista.carregar_precos(), generos)
    leitor = LeitorExploracao(historico, pasta)
    t = threading.Thread(target=_laco, args=(leitor, historico, estado_cliente, intervalo),
                         daemon=True, name="exploracao")
    t.start()
    return t
