#!/usr/bin/env python3
"""
setup.py — Preparação de dados para a PWA CED Map
Executa UMA VEZ para baixar os dados geográficos e converter o banco.

Uso:
    cd ced-map-pwa
    python setup.py

Requer: requests, pandas (já instalados no ambiente da dissertação)
"""

import json
import sys
import urllib.request
from pathlib import Path

# Garantir UTF-8 no stdout (Windows)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE = Path(__file__).parent
DATA = BASE / "data"
BANCO_CSV = BASE.parent / "BANCO_UNIFICADO_CED.csv"

# ── URLs dos dados geográficos (Natural Earth via GitHub) ─────────────────────
NE_BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"
GEO_FILES = {
    "ne_110m_countries.geojson":  f"{NE_BASE}/ne_110m_admin_0_countries.geojson",
    "ne_10m_admin1.geojson":      f"{NE_BASE}/ne_10m_admin_1_states_provinces.geojson",
}


def download(url: str, dest: Path):
    if dest.exists():
        print(f"  ✓ {dest.name} já existe, pulando")
        return
    print(f"  ↓ Baixando {dest.name}...", end=" ", flush=True)
    try:
        urllib.request.urlretrieve(url, dest)
        size_kb = dest.stat().st_size // 1024
        print(f"{size_kb} KB")
    except Exception as e:
        print(f"ERRO: {e}")
        print(f"    Baixe manualmente de: {url}")
        print(f"    Salve em: {dest}")


def convert_banco():
    """Converte BANCO_UNIFICADO_CED.csv → data/banco.json"""
    import pandas as pd

    out = DATA / "banco.json"
    if not BANCO_CSV.exists():
        print(f"  [ERRO] {BANCO_CSV} não encontrado.")
        print("  Execute build_banco_unificado.py primeiro.")
        return False

    print(f"  Convertendo {BANCO_CSV.name} → banco.json...", end=" ", flush=True)
    df = pd.read_csv(BANCO_CSV, dtype=str).fillna("")

    # Converter ano para int onde possível
    def parse_int(v):
        try:
            return int(float(v)) if v else None
        except (ValueError, TypeError):
            return None

    records = []
    for _, row in df.iterrows():
        rec = row.to_dict()
        rec["ano"] = parse_int(rec.get("ano", ""))
        rec["id"]  = parse_int(rec.get("id", ""))
        rec["verificado"] = str(rec.get("verificado", "")).lower() in ("true", "1", "yes")
        records.append(rec)

    out.write_text(json.dumps(records, ensure_ascii=False, indent=None), encoding="utf-8")
    size_kb = out.stat().st_size // 1024
    print(f"{len(records)} entradas, {size_kb} KB")
    return True


def slim_admin1():
    """
    Reduz o arquivo admin1 (~20MB) para apenas os campos necessários (~4MB).
    Mantém: name, admin, adm0_a3, postal, abbrev + geometry
    """
    import json

    src = DATA / "ne_10m_admin1.geojson"
    out = DATA / "ne_10m_admin1_slim.geojson"

    if out.exists():
        print(f"  ✓ {out.name} já existe, pulando")
        return

    if not src.exists():
        print(f"  [AVISO] {src.name} não encontrado, pulando slim.")
        return

    print(f"  Reduzindo ne_10m_admin1.geojson...", end=" ", flush=True)
    KEEP_PROPS = {"name", "admin", "adm0_a3", "postal", "abbrev", "iso_3166_2"}

    with open(src, encoding="utf-8") as f:
        gj = json.load(f)

    for feat in gj["features"]:
        props = feat.get("properties", {})
        feat["properties"] = {k: props.get(k, "") for k in KEEP_PROPS}

    with open(out, "w", encoding="utf-8") as f:
        json.dump(gj, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = out.stat().st_size // 1024
    print(f"{size_kb} KB")


def serve():
    """Inicia servidor HTTP local para desenvolvimento."""
    import http.server
    import threading

    PORT = 8080
    Handler = http.server.SimpleHTTPRequestHandler

    class QuietHandler(Handler):
        def log_message(self, *_):
            pass

    server = http.server.HTTPServer(("", PORT), QuietHandler)
    url = f"http://localhost:{PORT}"
    print(f"\n  Servidor rodando em {url}")
    print("  Pressione Ctrl+C para parar.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Servidor parado.")


def main():
    print("=" * 50)
    print("CED MAP — Setup de dados")
    print("=" * 50)

    print("\n[1] Dados geográficos:")
    for filename, url in GEO_FILES.items():
        download(url, DATA / filename)

    print("\n[2] Banco de dados:")
    convert_banco()

    print("\n[3] Otimizando admin-1:")
    slim_admin1()

    print("\n" + "=" * 50)
    print("Setup concluído! Para abrir a PWA:")
    print(f"  cd {BASE}")
    print(f"  python setup.py serve")
    print(f"  Acesse: http://localhost:8080")
    print("=" * 50)

    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        serve()


if __name__ == "__main__":
    main()
