"""Ponto de entrada do cliente: sobe o painel e roda o monitor."""

import sys
import time
import webbrowser

import config_cliente
import estado
import monitor
import painel

INTERVALO_ESPERA_OCIOSA_SEGUNDOS = 3600


def _aguardar_ate_interromper():
    """Mantém o processo (e o painel) no ar até Ctrl+C ou fechar a janela."""
    while True:
        time.sleep(INTERVALO_ESPERA_OCIOSA_SEGUNDOS)


def main(aguardar=_aguardar_ate_interromper):
    estado_cliente = estado.EstadoCliente()

    try:
        config = config_cliente.carregar_config()
    except config_cliente.ConfigInvalida as e:
        # Sobe o painel mesmo com config inválida: sem isso a mensagem só
        # existia no terminal, e o caso mais comum é a pessoa esquecer de
        # colar o token no config.txt e não entender por que nada aparece.
        estado_cliente.registrar_erro(str(e))
        _, porta = painel.iniciar_painel(estado_cliente)
        url = f"http://127.0.0.1:{porta}"

        print(f"\n[CONFIGURAÇÃO] {e}")
        print(f"Painel em {url} (mostra este erro).")
        print("Feche esta janela para encerrar.\n")

        try:
            aguardar()
        except KeyboardInterrupt:
            print("\nEncerrado.")
        return 1

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
