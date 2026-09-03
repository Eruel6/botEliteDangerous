"""Ponto de entrada do cliente: sobe o painel e roda o monitor."""

import sys
import webbrowser

import config_cliente
import estado
import monitor
import painel


def main():
    try:
        config = config_cliente.carregar_config()
    except config_cliente.ConfigInvalida as e:
        print(f"\n[CONFIGURAÇÃO] {e}\n")
        return 1

    estado_cliente = estado.EstadoCliente()
    _, porta = painel.iniciar_painel(estado_cliente)
    url = f"http://127.0.0.1:{porta}"

    print(f"Painel em {url}")
    print(f"Enviando para {config.api_url}")
    print("Feche esta janela para parar.\n")
    webbrowser.open(url)

    try:
        monitor.rodar(config, estado_cliente)
    except KeyboardInterrupt:
        print("\nEncerrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
