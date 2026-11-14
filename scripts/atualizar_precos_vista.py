# scripts/atualizar_precos_vista.py
"""Atualiza precos_vista.json a partir do site (ou de um HTML local com --html)."""
import argparse
import datetime
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import precos_vista

URL = "https://ed-dsn.net/en/vista-genomics-values/"
MINIMO_ESPECIES = 90


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--html", help="usa este arquivo HTML em vez de baixar do site")
    args = ap.parse_args(argv)

    if args.html:
        with open(args.html, encoding="utf-8") as f:
            html = f.read()
    else:
        import requests

        resp = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        resp.raise_for_status()
        html = resp.text

    especies = precos_vista.extrair_precos_do_html(html)
    if len(especies) < MINIMO_ESPECIES:
        sys.exit(
            f"Só {len(especies)} espécies extraídas (mínimo {MINIMO_ESPECIES}): "
            "o layout do site mudou? precos_vista.json não foi alterado."
        )

    apelidos = {}
    if os.path.exists(precos_vista.CAMINHO_PADRAO):
        with open(precos_vista.CAMINHO_PADRAO, encoding="utf-8") as f:
            apelidos = json.load(f).get("apelidos", {})

    dados = {
        "fonte": URL,
        "atualizado_em": datetime.date.today().isoformat(),
        "especies": especies,
        "apelidos": apelidos,
    }
    with open(precos_vista.CAMINHO_PADRAO, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print(f"{len(especies)} espécies gravadas em {precos_vista.CAMINHO_PADRAO}")


if __name__ == "__main__":
    main()
