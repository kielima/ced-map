#!/usr/bin/env python3
"""
build_admin2_polygons.py — Polígonos admin-2 (município/condado) dos top-5 países.

Baixa GADM v4.1 admin-2 para KOR, USA, CAN, JPN, DEU, simplifica geometria
(shapely) e exporta um único GeoJSON slim para uso na PWA.

Saída: data/admin2_top5.geojson

Uso:
    pip install requests shapely
    python build/build_admin2_polygons.py

Sobre PMTiles
─────────────
Para converter o GeoJSON resultante em PMTiles (mais leve e tileado):

    # Linux/macOS (WSL no Windows):
    tippecanoe -zg -o data/admin2_top5.pmtiles --drop-densest-as-needed \
               --extend-zooms-if-still-dropping data/admin2_top5.geojson

    # Hospedar admin2_top5.pmtiles em GitHub Releases (sem limite de tamanho)
    # e ajustar URL no app.js (loadAdmin2Layer)

Por que não escrevemos PMTiles direto em Python? Encoder MVT correto (com clipping,
quantização, simplificação por zoom e topologia) é um projeto à parte. A rota
GeoJSON simplificado + tippecanoe externo é mais robusta. A PWA também aceita o
GeoJSON direto (lazy-load em zoom alto), com performance aceitável até ~30 MB.
"""

import json
import sys
import urllib.request
import zipfile
from pathlib import Path

BASE = Path(__file__).parent
PWA_DATA = BASE.parent / "data"
DOWNLOADS = BASE / "_downloads"

# Top-5 países com maior densidade de jurisdições sub-nacionais no banco.
# (EU está fora porque não é um país com fronteiras GADM próprias.)
TOP5 = ["KOR", "USA", "CAN", "JPN", "DEU"]

GADM_BASE = "https://geodata.ucdavis.edu/gadm/gadm4.1/json"

# Tolerância de simplificação Douglas-Peucker em graus (~111 km por grau).
# 0.005 ≈ 500 m — suficiente para zoom até ~10 sem perder reconhecimento visual.
SIMPLIFY_TOL = 0.005

# Propriedades a manter na saída (descarta GID_0..GID_2, COUNTRY, NL_NAME etc.)
KEEP_PROPS = ("NAME_1", "NAME_2", "ISO_3")


def ensure_dirs():
    DOWNLOADS.mkdir(exist_ok=True)
    PWA_DATA.mkdir(exist_ok=True)


def download(iso3: str) -> Path:
    """Baixa e descompacta o admin-2 GADM v4.1 para o país. Retorna caminho do .json."""
    json_path = DOWNLOADS / f"gadm41_{iso3}_2.json"
    if json_path.exists():
        return json_path

    zip_path = DOWNLOADS / f"gadm41_{iso3}_2.json.zip"
    if not zip_path.exists():
        url = f"{GADM_BASE}/gadm41_{iso3}_2.json.zip"
        print(f"  ↓ {url} ...", end=" ", flush=True)
        try:
            urllib.request.urlretrieve(url, zip_path)
        except Exception as e:
            print(f"ERRO: {e}")
            return None
        size_mb = zip_path.stat().st_size / 1024 / 1024
        print(f"{size_mb:.1f} MB")

    with zipfile.ZipFile(zip_path) as zf:
        # GADM zips contêm um único .json com nome variável; pegar o primeiro
        names = [n for n in zf.namelist() if n.endswith(".json")]
        if not names:
            print(f"  [ERRO] {zip_path.name} não contém .json")
            return None
        zf.extract(names[0], DOWNLOADS)
        extracted = DOWNLOADS / names[0]
        if extracted != json_path:
            extracted.rename(json_path)
    return json_path


def simplify_feature(feat: dict, tolerance: float) -> dict | None:
    """Aplica simplificação Douglas-Peucker via shapely. Retorna feature ou None."""
    try:
        from shapely.geometry import shape, mapping
    except ImportError:
        print("[ERRO] shapely não instalado. pip install shapely", file=sys.stderr)
        sys.exit(1)

    geom = shape(feat["geometry"])
    geom = geom.simplify(tolerance, preserve_topology=True)
    if geom.is_empty:
        return None
    props = feat.get("properties") or {}
    slim_props = {k: props.get(k) for k in KEEP_PROPS if k in props}
    return {
        "type": "Feature",
        "properties": slim_props,
        "geometry": mapping(geom),
    }


def process_country(iso3: str) -> list[dict]:
    """Baixa, lê e simplifica o admin-2 de um país. Retorna lista de features slim."""
    print(f"\n[{iso3}]")
    json_path = download(iso3)
    if not json_path:
        return []

    print(f"  Lendo {json_path.name}...", end=" ", flush=True)
    with open(json_path, encoding="utf-8") as f:
        gj = json.load(f)
    raw = gj.get("features", [])
    print(f"{len(raw)} features brutos")

    print(f"  Simplificando (tol={SIMPLIFY_TOL})...", end=" ", flush=True)
    slim_features = []
    for feat in raw:
        f = simplify_feature(feat, SIMPLIFY_TOL)
        if f:
            # Garantir ISO_3 (algumas exports do GADM têm em GID_0)
            if "ISO_3" not in f["properties"]:
                gid0 = (feat.get("properties") or {}).get("GID_0")
                if gid0:
                    f["properties"]["ISO_3"] = gid0
            slim_features.append(f)
    print(f"{len(slim_features)} features após simplificação")
    return slim_features


def main():
    ensure_dirs()
    all_features: list[dict] = []
    for iso3 in TOP5:
        all_features.extend(process_country(iso3))

    out = PWA_DATA / "admin2_top5.geojson"
    print(f"\nGravando {out}...", end=" ", flush=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(
            {"type": "FeatureCollection", "features": all_features},
            f, ensure_ascii=False, separators=(",", ":"),
        )
    size_mb = out.stat().st_size / 1024 / 1024
    print(f"{size_mb:.1f} MB · {len(all_features)} features")

    print("\nPróximo passo: o app.js carrega data/admin2_top5.geojson automaticamente")
    print("ao chegar em zoom ≥ 6. Para converter em PMTiles, ver docstring deste script.")


if __name__ == "__main__":
    main()
