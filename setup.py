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

BASE      = Path(__file__).parent
DATA      = BASE / "data"
# Localização do CSV gerado por build/build_banco_unificado.py
BANCO_CSV = BASE / "build" / "BANCO_UNIFICADO_CED.csv"

# ── URLs dos dados geográficos (Natural Earth via GitHub) ─────────────────────
NE_BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"
GEO_FILES = {
    "ne_110m_countries.geojson":  f"{NE_BASE}/ne_110m_admin_0_countries.geojson",
    "ne_50m_admin1.geojson":      f"{NE_BASE}/ne_50m_admin_1_states_provinces.geojson",
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

    def parse_float(v):
        try:
            f = float(v)
            return f if f == f else None  # NaN check
        except (ValueError, TypeError):
            return None

    # Padrões que indicam credenciais/tokens em URLs — não publicar no repo
    CREDENTIAL_PATTERNS = ("X-Amz-Credential", "X-Amz-Signature", "AWSAccessKeyId")

    records = []
    for _, row in df.iterrows():
        rec = row.to_dict()
        rec["ano"]         = parse_int(rec.get("ano", ""))
        rec["id"]          = parse_int(rec.get("id", ""))
        rec["adm1_ne_id"]  = parse_int(rec.get("adm1_ne_id", ""))
        rec["lat"]         = parse_float(rec.get("lat", ""))
        rec["lon"]         = parse_float(rec.get("lon", ""))
        rec["verificado"]  = str(rec.get("verificado", "")).lower() in ("true", "1", "yes")

        # Remover URLs com credenciais AWS/assinadas (S3 pre-signed URLs)
        for url_field in ("url_documento", "url_referencia"):
            url_val = rec.get(url_field, "") or ""
            if any(pat in url_val for pat in CREDENTIAL_PATTERNS):
                rec[url_field] = ""

        records.append(rec)

    out.write_text(json.dumps(records, ensure_ascii=False, indent=None), encoding="utf-8")
    size_kb = out.stat().st_size // 1024
    print(f"{len(records)} entradas, {size_kb} KB")
    return True


def slim_admin1():
    """
    Reduz o arquivo 50m admin1 para apenas os campos necessários.
    Mantém: ne_id (join key), name, adm0_a3, iso_3166_2 + geometry
    O ne_id é o ID estável do Natural Earth, usado como promoteId no MapLibre.
    """
    import json

    src = DATA / "ne_50m_admin1.geojson"
    out = DATA / "ne_50m_admin1_slim.geojson"

    if out.exists():
        print(f"  ✓ {out.name} já existe, pulando")
        return

    if not src.exists():
        print(f"  [AVISO] {src.name} não encontrado, pulando slim.")
        return

    print(f"  Reduzindo ne_50m_admin1.geojson...", end=" ", flush=True)
    # ne_id é crítico — é o join key entre banco.json e o GeoJSON
    KEEP_PROPS = {"ne_id", "name", "adm0_a3", "iso_3166_2"}

    with open(src, encoding="utf-8") as f:
        gj = json.load(f)

    for feat in gj["features"]:
        props = feat.get("properties", {})
        # Usar .get(k) sem default para preservar tipos (ne_id é int, não str)
        feat["properties"] = {k: props.get(k) for k in KEEP_PROPS}

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

    print("\n[3] Otimizando admin-1 (50m):")
    slim_admin1()

    print("\n" + "=" * 50)
    print("Setup concluído!")
    print("Fluxo recomendado para rebuild completo:")
    print("  1. python ced-map-pwa/setup.py        (baixar geo + slim)")
    print("  2. python build_banco_unificado.py    (banco com adm1_ne_id)")
    print("  3. python ced-map-pwa/setup.py        (converter banco.csv → banco.json)")
    print(f"\nPara testar localmente:")
    print(f"  cd {BASE}")
    print(f"  python setup.py serve")
    print(f"  Acesse: http://localhost:8080")
    print("=" * 50)

    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        serve()


if __name__ == "__main__":
    main()
