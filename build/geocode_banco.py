#!/usr/bin/env python3
"""
geocode_banco.py — Geocodificador batch para o BANCO_UNIFICADO_CED.

Para cada entidade sub-nacional única (estadual + municipal) do banco, consulta
o Nominatim (OpenStreetMap) respeitando a política de uso (1 req/s, User-Agent
identificável) e guarda o resultado em build/geocodes.json. O cache é incremental:
re-execuções aproveitam o que já foi resolvido e só consultam o que falta.

Uso:
    pip install requests pandas
    python build/geocode_banco.py                 # geocodifica tudo o que falta
    python build/geocode_banco.py --retry-failed  # tenta de novo entradas marcadas como falhas
    python build/geocode_banco.py --limit 50      # geocodifica no máximo 50 entidades novas

O script é seguro de interromper (Ctrl+C): o cache é gravado em disco a cada N
consultas (default 10) e antes de sair.
"""

import argparse
import json
import re
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BASE       = Path(__file__).parent
CACHE_PATH = BASE / "geocodes.json"
BANCO_CSV  = BASE / "BANCO_UNIFICADO_CED.csv"

# Política de uso do Nominatim: identificar app + e-mail de contato.
# Trocar pelo seu contato se forkar este projeto.
USER_AGENT = "ced-map/1.0 (kly@sapo.pt; https://github.com/kielima/ced-map)"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Política: máximo 1 req/s. Usamos 1.1s de folga para evitar 429.
SLEEP_SECONDS = 1.1

# Salvar o cache a cada N consultas bem-sucedidas.
SAVE_EVERY = 10

# ISO-3 → ISO-2 (códigos de país para o parâmetro `countrycodes` do Nominatim).
# Restrito aos países presentes no banco (parsing falha silenciosamente se faltar).
ISO3_TO_ISO2 = {
    "AUS": "au", "AUT": "at", "BEL": "be", "CAN": "ca", "CHL": "cl",
    "COL": "co", "CZE": "cz", "FIN": "fi", "FRA": "fr", "DEU": "de",
    "HUN": "hu", "IRL": "ie", "ITA": "it", "JPN": "jp", "LTU": "lt",
    "NLD": "nl", "NOR": "no", "PHL": "ph", "POL": "pl", "SVK": "sk",
    "SLB": "sb", "KOR": "kr", "ESP": "es", "SWE": "se", "CHE": "ch",
    "TWN": "tw", "GBR": "gb", "USA": "us", "BRA": "br", "NZL": "nz",
    "PER": "pe", "SGP": "sg", "FJI": "fj", "VUT": "vu", "ARG": "ar",
    "MEX": "mx", "PRT": "pt", "AND": "ad", "BGD": "bd", "MLT": "mt",
    "MDV": "mv", "VAT": "va", "JEY": "je", "GIB": "gi", "IMN": "im",
    "MUS": "mu", "CHN": "cn", "IND": "in", "PAK": "pk", "RUS": "ru",
    "IRN": "ir", "IRQ": "iq", "SYR": "sy", "AFG": "af", "NPL": "np",
    "MAR": "ma", "DZA": "dz", "NGA": "ng", "SOM": "so", "ETH": "et",
    "KEN": "ke", "ZAF": "za", "MOZ": "mz", "MDG": "mg", "MWI": "mw",
    "ARE": "ae", "OMN": "om", "TUR": "tr", "GRC": "gr", "CYP": "cy",
    "BWA": "bw", "SSD": "ss", "MHL": "mh", "LUX": "lu",
}

# Para construir queries em inglês (o Nominatim entende várias línguas, mas
# a forma canônica em inglês costuma dar a melhor taxa de acerto).
ISO3_TO_EN = {
    "AUS": "Australia", "AUT": "Austria", "BEL": "Belgium", "CAN": "Canada",
    "CHL": "Chile", "COL": "Colombia", "CZE": "Czechia", "FIN": "Finland",
    "FRA": "France", "DEU": "Germany", "HUN": "Hungary", "IRL": "Ireland",
    "ITA": "Italy", "JPN": "Japan", "LTU": "Lithuania", "NLD": "Netherlands",
    "NOR": "Norway", "PHL": "Philippines", "POL": "Poland", "SVK": "Slovakia",
    "SLB": "Solomon Islands", "KOR": "South Korea", "ESP": "Spain",
    "SWE": "Sweden", "CHE": "Switzerland", "TWN": "Taiwan",
    "GBR": "United Kingdom", "USA": "United States", "BRA": "Brazil",
    "NZL": "New Zealand", "PER": "Peru", "SGP": "Singapore", "FJI": "Fiji",
    "VUT": "Vanuatu", "ARG": "Argentina", "MEX": "Mexico", "PRT": "Portugal",
    "AND": "Andorra", "BGD": "Bangladesh", "MLT": "Malta", "MDV": "Maldives",
    "VAT": "Vatican City", "JEY": "Jersey", "GIB": "Gibraltar",
    "IMN": "Isle of Man", "MUS": "Mauritius", "MHL": "Marshall Islands",
    "LUX": "Luxembourg",
}


# ── Cache I/O ─────────────────────────────────────────────────────────────────

def load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  [AVISO] Cache inválido ({e}). Recomeçando.")
        return {}


def save_cache(cache: dict) -> None:
    tmp = CACHE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CACHE_PATH)


# ── Normalização de chaves ────────────────────────────────────────────────────

def cache_key(iso3: str, regiao: str, entidade: str) -> str:
    """Chave estável de cache. Insensível a espaços extras."""
    parts = [(iso3 or "").strip().upper(),
             re.sub(r"\s+", " ", (regiao or "").strip()),
             re.sub(r"\s+", " ", (entidade or "").strip())]
    return "|".join(parts)


def clean_entity_name(name: str) -> str:
    """Remove sufixos genéricos que confundem o Nominatim.

    Ex.: 'City of Berkeley Council' → 'Berkeley'
         'Toronto City Council'     → 'Toronto'
         'Agematsu Town (上松町)'   → 'Agematsu'
         'Acton Town Meeting'       → 'Acton'
         'Buk-gu (부산 북구), Busan' → 'Buk-gu'
    """
    n = name
    # Remover parênteses com caracteres CJK (japonês/coreano/chinês)
    n = re.sub(r"\s*\([　-鿿가-힯\s]+\)", "", n)
    # Remover sufixo após vírgula (ex.: "Buk-gu, Busan" → "Buk-gu")
    # Mantém só a primeira parte se houver vírgula
    if "," in n:
        n = n.split(",", 1)[0]
    # Remover prefixos
    n = re.sub(r"^(city of|town of|district of|municipality of|borough of)\s+",
               "", n, flags=re.IGNORECASE)
    # Remover sufixos governamentais (em loop, pois alguns são compostos)
    suffix_re = re.compile(
        r"\s+(city council|town council|borough council|district council|"
        r"county council|municipal council|town meeting|town board|"
        r"common meeting|common council|board of commissioners|"
        r"city commission|county commission|council|parliament|assembly|"
        r"legislative assembly|government|town|city|village|municipality|"
        r"shire|borough|district|county|province|prefecture)\s*$",
        flags=re.IGNORECASE,
    )
    for _ in range(4):  # até 4 sufixos compostos
        new_n = suffix_re.sub("", n).strip()
        if new_n == n.strip() or not new_n:
            break
        n = new_n
    return n.strip() or name.strip()


# ── Consulta Nominatim ────────────────────────────────────────────────────────

class GeocoderError(Exception):
    pass


def query_nominatim(query: str, country_iso2: str, session: requests.Session) -> dict | None:
    """Faz uma chamada ao Nominatim. Retorna primeiro resultado ou None."""
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "addressdetails": 0,
    }
    if country_iso2:
        params["countrycodes"] = country_iso2

    try:
        r = session.get(NOMINATIM_URL, params=params, timeout=15)
    except requests.RequestException as e:
        raise GeocoderError(f"erro de rede: {e}") from e

    if r.status_code == 429:
        raise GeocoderError("rate limit (HTTP 429) — aguarde e tente novamente")
    if r.status_code >= 500:
        raise GeocoderError(f"HTTP {r.status_code} no Nominatim")
    if r.status_code != 200:
        raise GeocoderError(f"HTTP {r.status_code}: {r.text[:200]}")

    data = r.json()
    if not data:
        return None
    return data[0]


def geocode_entity(iso3: str, regiao: str, entidade: str,
                   session: requests.Session) -> dict:
    """Tenta múltiplas variações de query. Retorna dict do cache (com `ok`)."""
    iso2     = ISO3_TO_ISO2.get(iso3, "")
    country  = ISO3_TO_EN.get(iso3, "")
    cleaned  = clean_entity_name(entidade)

    # Estratégia: do mais específico ao mais genérico.
    candidates = []
    if regiao and cleaned:
        candidates.append(f"{cleaned}, {regiao}, {country}".strip(", "))
    if cleaned:
        candidates.append(f"{cleaned}, {country}".strip(", "))
    # Fallback final: nome bruto + país
    if entidade != cleaned:
        candidates.append(f"{entidade}, {country}".strip(", "))
    # Dedup mantendo ordem
    seen = set()
    candidates = [c for c in candidates if c and not (c in seen or seen.add(c))]

    last_err = None
    for q in candidates:
        try:
            hit = query_nominatim(q, iso2, session)
        except GeocoderError as e:
            last_err = str(e)
            time.sleep(SLEEP_SECONDS)
            continue

        time.sleep(SLEEP_SECONDS)
        if hit:
            return {
                "lat":  float(hit["lat"]),
                "lon":  float(hit["lon"]),
                "display_name": hit.get("display_name", ""),
                "query": q,
                "ok": True,
                "queried_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }

    return {
        "lat": None,
        "lon": None,
        "display_name": "",
        "query": candidates[-1] if candidates else "",
        "ok": False,
        "error": last_err or "sem resultado",
        "queried_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


# ── Pipeline ──────────────────────────────────────────────────────────────────

def unique_targets(banco_csv: Path) -> list[tuple[str, str, str]]:
    """Lê o banco e retorna lista de (iso3, regiao, entidade) únicos a geocodificar.

    Apenas entradas sub-nacionais (estadual + municipal) com iso_3 conhecido.
    """
    import pandas as pd

    df = pd.read_csv(banco_csv, dtype=str).fillna("")
    df = df[df["nivel"].isin(("estadual", "municipal"))]
    df = df[df["iso_3"].str.len() > 0]

    pairs: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for _, row in df.iterrows():
        key = (row["iso_3"].strip().upper(),
               row["regiao"].strip(),
               row["entidade"].strip())
        if key in seen or not key[2]:
            continue
        seen.add(key)
        pairs.append(key)
    return pairs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--retry-failed", action="store_true",
                    help="reconsulta entradas marcadas como ok=false")
    ap.add_argument("--limit", type=int, default=0,
                    help="máximo de novas consultas nesta execução (0 = sem limite)")
    args = ap.parse_args()

    if not BANCO_CSV.exists():
        print(f"[ERRO] {BANCO_CSV} não encontrado. Rode build_banco_unificado.py primeiro.")
        sys.exit(1)

    cache = load_cache()
    print(f"Cache atual: {len(cache)} entradas em {CACHE_PATH.name}")

    targets = unique_targets(BANCO_CSV)
    print(f"Alvos sub-nacionais únicos: {len(targets)}")

    # Filtrar o que já está no cache (e está OK, ou foi falha mas --retry-failed)
    todo: list[tuple[str, str, str]] = []
    for iso3, regiao, entidade in targets:
        k = cache_key(iso3, regiao, entidade)
        existing = cache.get(k)
        if existing is None:
            todo.append((iso3, regiao, entidade))
        elif args.retry_failed and not existing.get("ok"):
            todo.append((iso3, regiao, entidade))

    if args.limit:
        todo = todo[: args.limit]

    print(f"A consultar nesta execução: {len(todo)}")
    if not todo:
        print("Nada a fazer. Cache já cobre todos os alvos.")
        return

    eta_min = (len(todo) * SLEEP_SECONDS) / 60
    print(f"Tempo estimado: ~{eta_min:.1f} min (a {SLEEP_SECONDS:.1f}s por consulta)")
    print()

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    # Persistir cache em saídas inesperadas (Ctrl+C, SIGTERM)
    def _on_signal(sig, _frame):
        print(f"\nSinal {sig} recebido. Salvando cache...")
        save_cache(cache)
        sys.exit(130)
    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    new_hits = 0
    new_miss = 0
    since_save = 0

    for i, (iso3, regiao, entidade) in enumerate(todo, 1):
        k = cache_key(iso3, regiao, entidade)
        label = f"{entidade}" + (f" / {regiao}" if regiao else "") + f" [{iso3}]"
        print(f"[{i}/{len(todo)}] {label[:80]}", end=" → ", flush=True)
        try:
            res = geocode_entity(iso3, regiao, entidade, session)
        except KeyboardInterrupt:
            print("interrompido pelo usuário.")
            break

        cache[k] = res
        since_save += 1
        if res["ok"]:
            new_hits += 1
            print(f"OK ({res['lat']:.4f}, {res['lon']:.4f})")
        else:
            new_miss += 1
            print(f"MISS ({res.get('error', '?')})")

        if since_save >= SAVE_EVERY:
            save_cache(cache)
            since_save = 0

    save_cache(cache)
    print()
    print(f"Concluído. Novos hits: {new_hits} · falhas: {new_miss}")
    print(f"Cache total: {len(cache)} entradas em {CACHE_PATH.name}")
    print("\nPróximo passo: python build/build_banco_unificado.py && python setup.py")


if __name__ == "__main__":
    main()
