import json
import os
import time

def extrair_materiais_construcao(caminho_arquivo_log):
    ultima_lista_valida = []
    nome_instalacao = "Desconhecida"
    linha_lista = -1

    with open(caminho_arquivo_log, 'r', encoding='utf-8') as f:
        log_content = f.readlines()

    for line_number, line in enumerate(log_content):
        try:
            registro = json.loads(line)
            if isinstance(registro, list) and all(
                'Name_Localised' in x and 'RequiredAmount' in x and 'ProvidedAmount' in x for x in registro
            ):
                ultima_lista_valida = registro
                linha_lista = line_number
            elif isinstance(registro, dict):
                for valor in registro.values():
                    if isinstance(valor, list) and all(
                        isinstance(x, dict) and 'Name_Localised' in x and
                        'RequiredAmount' in x and 'ProvidedAmount' in x
                        for x in valor
                    ):
                        ultima_lista_valida = valor
                        linha_lista = line_number
        except json.JSONDecodeError:
            continue

    # Tentar encontrar instalação relacionada mais próxima acima da linha da lista
    for i in range(linha_lista, -1, -1):
        try:
            registro = json.loads(log_content[i])
            if registro.get("event") == "ApproachSettlement":
                nome = registro.get("Name", "")
                if nome.startswith("Planetary Construction Site:"):
                    nome_instalacao = nome
                    break
        except json.JSONDecodeError:
            continue

    return ultima_lista_valida, nome_instalacao


def imprimir_tabela_materiais(materiais, nome_instalacao="Desconhecida"):
    print(f"\n📍 Materiais para instalação: {nome_instalacao}\n")
    header = ["Material", "Requisitado", "Fornecido", "Faltando"]
    col_widths = [max(len(str(m.get("Name_Localised", ""))) for m in materiais + [{"Name_Localised": header[0]}])]
    col_widths += [len(header[1]), len(header[2]), len(header[3])]

    print(f"{header[0]:<{col_widths[0]}} | {header[1]:>{col_widths[1]}} | {header[2]:>{col_widths[2]}} | {header[3]:>{col_widths[3]}}")
    print("-" * (sum(col_widths) + 9))

    for m in materiais:
        if all(k in m for k in ("Name_Localised", "RequiredAmount", "ProvidedAmount")):
            nome = m["Name_Localised"]
            req = m["RequiredAmount"]
            prov = m["ProvidedAmount"]
            faltando = req - prov
            print(f"{nome:<{col_widths[0]}} | {req:>{col_widths[1]}} | {prov:>{col_widths[2]}} | {faltando:>{col_widths[3]}}")


if __name__ == "__main__":
    caminho_log = "Journal.2025-05-20T141829.01.log"  # ajuste para o nome correto

    print("⏳ Monitorando o log a cada 3 minutos...\n(Pressione Ctrl+C para interromper)")
    while True:
        if os.path.exists(caminho_log):
            materiais, nome_instalacao = extrair_materiais_construcao(caminho_log)
            if materiais:
                imprimir_tabela_materiais(materiais, nome_instalacao)
            else:
                print("⚠️ Nenhuma entrada de materiais de construção encontrada.")
        else:
            print(f"❌ Arquivo não encontrado: {caminho_log}")

        time.sleep(180)  # aguardar 3 minutos