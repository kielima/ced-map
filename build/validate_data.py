#!/usr/bin/env python3
"""
validate_data.py — Validador de integridade dos dados servidos pela PWA.

Verifica que:
- banco.json é JSON válido, lista não-vazia
- Todos os campos obrigatórios estão presentes na primeira entrada
- Valores de `nivel` e `cor_mapa` estão dentro do enum esperado
- manifest.json é JSON válido
- geocodes.json (se existir) é JSON válido

Usado pelo workflow .github/workflows/ci.yml como gate de qualidade.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent

REQUIRED_FIELDS = {"id", "pais", "iso_3", "nivel", "entidade",
                   "cor_mapa", "fonte", "status"}
VALID_NIVEIS    = {"nacional", "estadual", "municipal"}
VALID_CORES     = {"vermelho", "laranja", "amarelo", "azul", "roxo", "cinza"}


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    failed = False

    banco_path = REPO / "data" / "banco.json"
    print(f"Validando {banco_path}...")
    banco = load_json(banco_path)
    if not isinstance(banco, list) or not banco:
        print("[ERRO] banco.json não é uma lista não-vazia")
        return 1

    missing = REQUIRED_FIELDS - set(banco[0].keys())
    if missing:
        print(f"[ERRO] Campos obrigatórios em falta: {missing}")
        failed = True

    niveis = {e.get("nivel") for e in banco}
    invalid_niveis = niveis - VALID_NIVEIS
    if invalid_niveis:
        print(f"[ERRO] Níveis inválidos encontrados: {invalid_niveis}")
        failed = True

    cores = {e.get("cor_mapa") for e in banco}
    invalid_cores = cores - VALID_CORES
    if invalid_cores:
        print(f"[ERRO] Cores inválidas encontradas: {invalid_cores}")
        failed = True

    paises = {e["iso_3"] for e in banco if e.get("iso_3")}
    print(f"  OK — {len(banco)} entradas, {len(paises)} países")

    manifest_path = REPO / "manifest.json"
    print(f"Validando {manifest_path}...")
    load_json(manifest_path)
    print("  OK")

    geocodes_path = REPO / "build" / "geocodes.json"
    if geocodes_path.exists():
        print(f"Validando {geocodes_path}...")
        load_json(geocodes_path)
        print("  OK")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
