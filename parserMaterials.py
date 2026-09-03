"""Monitor de terminal: imprime a tabela de materiais da última instalação do log."""

import os
import time

import ed_parser

CAMINHO_LOG = os.path.join("journals", "Journal.2025-05-20T141829.01.log")
INTERVALO_SEGUNDOS = 180


def main():
    print("⏳ Monitorando o log a cada 3 minutos...\n(Pressione Ctrl+C para interromper)")
    while True:
        if os.path.exists(CAMINHO_LOG):
            instalacao = ed_parser.ultima_instalacao(CAMINHO_LOG)
            if instalacao:
                print(ed_parser.formatar_tabela_terminal(instalacao), end="")
            else:
                print("⚠️ Nenhuma entrada de materiais de construção encontrada.")
        else:
            print(f"❌ Arquivo não encontrado: {CAMINHO_LOG}")

        time.sleep(INTERVALO_SEGUNDOS)


if __name__ == "__main__":
    main()
