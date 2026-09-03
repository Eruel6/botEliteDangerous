# painel.py
"""Servidor HTTP local que mostra o estado do cliente.

Só leitura, só em 127.0.0.1, e só duas rotas explícitas — servir o diretório
exporia o config.txt, que tem o token de quem está rodando.
"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORTA_PADRAO = 8765
TENTATIVAS_DE_PORTA = 10
CAMINHO_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "painel.html")


def _criar_handler(estado_cliente):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/estado.json":
                self._responder(
                    200,
                    "application/json; charset=utf-8",
                    json.dumps(estado_cliente.como_dicionario(), ensure_ascii=False),
                )
            elif self.path in ("/", "/index.html"):
                with open(CAMINHO_HTML, encoding="utf-8") as f:
                    self._responder(200, "text/html; charset=utf-8", f.read())
            else:
                self._responder(404, "text/plain; charset=utf-8", "Não encontrado")

        def _responder(self, status, tipo, corpo):
            dados = corpo.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def log_message(self, *args):
            """Silencia o log de acesso: o painel é consultado a cada 5 s e
            encheria o terminal de ruído."""

    return Handler


def iniciar_painel(estado_cliente, porta=PORTA_PADRAO):
    """Sobe o painel numa thread daemon. Devolve (servidor, porta usada)."""
    handler = _criar_handler(estado_cliente)
    ultimo_erro = None

    for tentativa in range(TENTATIVAS_DE_PORTA):
        alvo = 0 if porta == 0 else porta + tentativa
        try:
            servidor = ThreadingHTTPServer(("127.0.0.1", alvo), handler)
        except OSError as e:
            ultimo_erro = e
            continue
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        return servidor, servidor.server_address[1]

    raise OSError(f"Nenhuma porta livre a partir de {porta}: {ultimo_erro}")
