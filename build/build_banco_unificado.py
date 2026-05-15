#!/usr/bin/env python3
"""
build_banco_unificado.py — Banco Unificado de Declarações de Emergência Climática

Consolida 4 fontes:
  1. cedamia_data.csv             → declarações formais CED (todos os níveis)
  2. CED data sheet.xlsx          → almost-CEDs (tentativas rejeitadas / linguagem divergente)
  3. ATRIBUICAO_CLIMATICA_WWA.md  → atribuição climática científica (WWA)
  4. Entradas manuais hardcodadas → declarações 2022-2026 não capturadas pelo CEDAMIA

Saída:
  BANCO_UNIFICADO_CED.csv   — formato plano para scripts Python / PWA
  BANCO_UNIFICADO_CED.xlsx  — para revisão manual no Excel
"""

import re
import sys
import pandas as pd
from pathlib import Path

# Quando executado dentro do repo (build/), BASE aponta para build/
# e PWA_DATA aponta para data/ na raiz do repo.
BASE     = Path(__file__).parent          # build/
PWA_DATA = BASE.parent / "data"           # ../data/ (onde mora o GeoJSON do MapLibre)

# ── Conjuntos de referência ───────────────────────────────────────────────────

NATIONAL_ISO = {
    "GBR", "IRL", "PRT", "CAN", "FRA", "ARG", "ESP", "AUT", "MLT", "BGD",
    "ITA", "AND", "MDV", "KOR", "JPN", "NZL", "SGP", "FJI", "MUS", "VUT",
    "MEX", "PER", "VAT", "JEY", "GIB", "IMN",
}

ATTRIBUTION_ISO = {
    "CHN", "IND", "PAK", "RUS", "IRN", "IRQ", "SYR", "AFG", "NPL", "MAR",
    "DZA", "NGA", "SOM", "ETH", "KEN", "ZAF", "MOZ", "MDG", "MWI", "ARE",
    "OMN", "TUR", "GRC", "CYP", "BWA", "SSD",
}

COUNTRY_TO_ISO3 = {
    "Australia":             "AUS",
    "Austria":               "AUT",
    "Belgium":               "BEL",
    "Canada":                "CAN",
    "Chile":                 "CHL",
    "Colombia":              "COL",
    "Czechia":               "CZE",
    "Finland":               "FIN",
    "France":                "FRA",
    "Germany":               "DEU",
    "Hungary":               "HUN",
    "Ireland, Republic of":  "IRL",
    "Italy":                 "ITA",
    "Japan":                 "JPN",
    "Lithuania":             "LTU",
    "Netherlands":           "NLD",
    "Norway":                "NOR",
    "Philippines":           "PHL",
    "Poland":                "POL",
    "Slovakia":              "SVK",
    "Solomon Islands":       "SLB",
    "South Korea":           "KOR",
    "Spain":                 "ESP",
    "Sweden":                "SWE",
    "Switzerland":           "CHE",
    "Taiwan":                "TWN",
    "UK and dependencies":   "GBR",
    "USA":                   "USA",
    "Brazil":                "BRA",
    "New Zealand":           "NZL",
    "Peru":                  "PER",
    "Singapore":             "SGP",
    "Fiji":                  "FJI",
    "Vanuatu":               "VUT",
    "Argentina":             "ARG",
    "Mexico":                "MEX",
    "Portugal":              "PRT",
    "Andorra":               "AND",
    "Bangladesh":            "BGD",
    "Malta":                 "MLT",
    "Maldives":              "MDV",
    "European Union":        None,
    # Territórios dependentes / micro-estados com iso próprio
    "Gibraltar":             "GIB",
    "Jersey":                "JEY",
    "Isle of Man":           "IMN",
    "Mauritius":             "MUS",
    "Holy See":              "VAT",
    "Vatican":               "VAT",
}

ISO3_TO_PT = {
    "AUS": "Austrália",         "AUT": "Áustria",           "BEL": "Bélgica",
    "CAN": "Canadá",            "CHL": "Chile",             "COL": "Colômbia",
    "CZE": "Tchéquia",          "FIN": "Finlândia",         "FRA": "França",
    "DEU": "Alemanha",          "HUN": "Hungria",           "IRL": "Irlanda",
    "ITA": "Itália",            "JPN": "Japão",             "LTU": "Lituânia",
    "NLD": "Países Baixos",     "NOR": "Noruega",           "PHL": "Filipinas",
    "POL": "Polônia",           "SVK": "Eslováquia",        "SLB": "Ilhas Salomão",
    "KOR": "Coreia do Sul",     "ESP": "Espanha",           "SWE": "Suécia",
    "CHE": "Suíça",             "TWN": "Taiwan",            "GBR": "Reino Unido",
    "USA": "Estados Unidos",    "BRA": "Brasil",            "NZL": "Nova Zelândia",
    "PER": "Peru",              "SGP": "Singapura",         "FJI": "Fiji",
    "VUT": "Vanuatu",           "ARG": "Argentina",         "MEX": "México",
    "PRT": "Portugal",          "AND": "Andorra",           "BGD": "Bangladesh",
    "MLT": "Malta",             "MDV": "Maldivas",          "VAT": "Vaticano",
    "JEY": "Jersey",            "GIB": "Gibraltar",         "IMN": "Ilha de Man",
    "MUS": "Maurícia",
    "CHN": "China",             "IND": "Índia",             "PAK": "Paquistão",
    "RUS": "Rússia",            "IRN": "Irã",               "IRQ": "Iraque",
    "SYR": "Síria",             "AFG": "Afeganistão",       "NPL": "Nepal",
    "MAR": "Marrocos",          "DZA": "Argélia",           "NGA": "Nigéria",
    "SOM": "Somália",           "ETH": "Etiópia",           "KEN": "Quênia",
    "ZAF": "África do Sul",     "MOZ": "Moçambique",        "MDG": "Madagascar",
    "MWI": "Malaui",            "ARE": "Emirados Árabes",   "OMN": "Omã",
    "TUR": "Turquia",           "GRC": "Grécia",            "CYP": "Chipre",
    "BWA": "Botsuana",          "SSD": "Sudão do Sul",
    "MHL": "Ilhas Marshall",    "LUX": "Luxemburgo",
}

# Padrões (lowercase) por ISO que identificam o órgão nacional principal.
# Se o nome da entidade contiver qualquer um desses padrões E o iso3 for o correto,
# → nivel="nacional", cor_mapa="vermelho"
NATIONAL_BODY_PATTERNS: dict[str, list[str]] = {
    "AND": ["general council"],
    "ARG": ["argentinian senate", "senate of argentina", "senado"],
    "AUT": ["austrian national council", "nationalrat", "national council (lower house)"],
    "BGD": ["bangladesh national assembly", "জাতীয় সংসদ"],
    "CAN": ["parliament of canada", "house of commons of canada", "canadian senate"],
    "ESP": ["spain - congress", "congress of deputies", "cortes generales"],
    "FJI": ["fiji parliament", "parliament of fiji"],
    "FRA": ["france - national parliament", "national parliament", "assemblée nationale"],
    "GBR": ["uk parliament", "house of commons", "parliament of the united kingdom"],
    "GIB": ["gibraltar parliament"],
    "IMN": ["tynwald", "isle of man parliament"],
    "IRL": ["dáil", "dail", "oireachtas"],
    "ITA": ["national parliament", "camera dei deputati", "chamber of deputies"],
    "JEY": ["states of jersey", "jersey parliament"],
    "JPN": ["japan national parliament", "national diet", "kokkai"],
    "KOR": ["south korea national assembly"],
    "MDV": ["majlis", "maldives parliament"],
    "MEX": ["mexico senate"],
    "MLT": ["malta national parliament", "national parliament"],
    "MUS": ["national assembly of mauritius", "mauritius parliament"],
    "NZL": ["new zealand parliament", "parliament of new zealand"],
    "PER": ["congress of peru", "congreso de la república", "peru (national)"],
    "PRT": ["assembly of the republic", "assembleia da república", "portugal assembly"],
    "SGP": ["singapore parliament"],
    "VAT": ["holy see", "vatican"],
    "VUT": ["vanuatu parliament", "parliament of vanuatu"],
}

# Palavras-chave de entidades ESTADUAIS/REGIONAIS (entre nacional e municipal)
STATE_KEYWORDS = [
    "parliament", "assembly", "legislative", "senate", "congress",
    "government", "prefecture", "canton", "regional council",
    "regional assembly", "state parliament", "diet",
    "landtag", "generalitat", "cortes", "junta", "bundesland", "kanton",
    "oblast", "province government", "provincial council", "voivodeship",
    "regional parliament", "senate region", "autonomous community",
    "state government", "territory government", "region council",
    "district council assembly",
    # NÃO incluir: "county council", "county government" (são nível municipal)
]

SCHEMA_COLS = [
    "pais", "iso_3", "nivel", "entidade", "regiao", "ano",
    "data_completa", "status", "fonte", "tipo_evidencia", "cor_mapa",
    "url_documento", "url_referencia", "fator_risco_wwa",
    "justificativa", "observacoes", "verificado",
    # Phase 2: join com Natural Earth admin-1 (ne_id inteiro, null se não casou)
    "adm1_ne_id",
]

# Mapeamento extra para nomes de países no xlsx almost-CEDs
ALMOST_COUNTRY_MAP = {
    "Britain":            "GBR",
    "UK":                 "GBR",
    "United Kingdom":     "GBR",
    "USA":                "USA",
    "United States":      "USA",
    "Marshall Islands":   "MHL",
    "Luxembourg":         "LUX",
    "New Zealand":        "NZL",
    "Ireland":            "IRL",
    "South Korea":        "KOR",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _s(cell) -> str:
    return str(cell).strip() if pd.notna(cell) and str(cell).strip() not in ("nan", "None") else ""

def looks_like_date(s: str) -> bool:
    return bool(re.match(r"\d{1,2}\s+\w+\s+20\d\d", s.strip()))

def is_national_body(name: str, iso3: str) -> bool:
    """Retorna True se a entidade é o órgão nacional principal desse país."""
    if iso3 not in NATIONAL_BODY_PATTERNS:
        return False
    n = name.lower()
    return any(pat in n for pat in NATIONAL_BODY_PATTERNS[iso3])

def is_state_level(name: str) -> bool:
    n = name.lower()
    return any(kw in n for kw in STATE_KEYWORDS)

def classify_nivel(name: str, iso3: str) -> tuple[str, str]:
    """Classifica o nível e a cor_mapa da entidade."""
    if iso3 in NATIONAL_ISO and is_national_body(name, iso3):
        return "nacional", "vermelho"
    if is_state_level(name):
        return "estadual", "laranja"
    return "municipal", "amarelo"

def extract_year(date_str: str):
    m = re.search(r"(20\d\d)", str(date_str))
    return int(m.group(1)) if m else None

def blank_row() -> dict:
    return {col: "" for col in SCHEMA_COLS}

# ── 1. Parser CEDAMIA CSV ─────────────────────────────────────────────────────

def parse_cedamia(csv_path: Path) -> list[dict]:
    print(f"\n[1] Parseando CEDAMIA: {csv_path.name}")
    df = pd.read_csv(csv_path, header=None, low_memory=False, dtype=str)

    SKIP_WORDS = {
        "no. of", "total", "conservative", "labour", "greens", "independent",
        "between", "less than", "greater", "population", "number of", "nations",
        "liberal", "council operations", "community-wide", "see note",
        "canada: the", "if minutes", "totals",
    }

    # ── Detectar inícios de seção de país ────────────────────────────────────
    country_starts: dict[int, str] = {}
    for i in range(6, len(df)):
        c0 = _s(df.iloc[i, 0])
        c1 = _s(df.iloc[i, 1])
        c2 = _s(df.iloc[i, 2])
        c3 = _s(df.iloc[i, 3])
        c4 = _s(df.iloc[i, 4])

        if not c0:
            continue
        if looks_like_date(c4) or looks_like_date(c3):
            continue
        lower = c0.lower()
        if any(w in lower for w in SKIP_WORDS):
            continue
        if c0.endswith(":") or "totals:" in lower:
            continue
        try:
            v = float(c3.replace(",", ""))
            if v > 1000 and len(c3) > 4:
                continue
        except ValueError:
            pass
        if "<-CED total" in c3 or (c1 == "" and c2 in [""] + [str(n) for n in range(1, 500)]):
            country_starts[i] = c0

    sorted_starts = sorted(country_starts.items())
    sections = [
        (row, sorted_starts[idx + 1][0] if idx + 1 < len(sorted_starts) else len(df), name)
        for idx, (row, name) in enumerate(sorted_starts)
    ]

    rows: list[dict] = []
    for start, end, country in sections:
        iso3 = COUNTRY_TO_ISO3.get(country)

        for i in range(start + 1, end):
            c0 = _s(df.iloc[i, 0])   # Jurisdição
            c1 = _s(df.iloc[i, 1])   # (sub-campo)
            c2 = _s(df.iloc[i, 2])   # Região/estado
            c4 = _s(df.iloc[i, 4])   # Data
            c7 = _s(df.iloc[i, 7])   # Tipo de declaração
            c8 = _s(df.iloc[i, 8])   # URL ata/moção
            c9 = _s(df.iloc[i, 9])   # URL artigo de mídia

            # Parar ao encontrar a seção de totais globais (depois do último país)
            if any(stop in c0.lower() for stop in ("total global", "significant declarations", "political control")):
                break

            if not (c0 and looks_like_date(c4)):
                continue

            region = c2 if (c2 and not c2.isdigit()) else (c1 if (c1 and not c1.isdigit()) else "")
            nivel, cor = classify_nivel(c0, iso3 or "")

            r = blank_row()
            r.update({
                "pais":           ISO3_TO_PT.get(iso3, country) if iso3 else country,
                "iso_3":          iso3 or "",
                "nivel":          nivel,
                "entidade":       c0,
                "regiao":         region,
                "ano":            extract_year(c4),
                "data_completa":  c4,
                "status":         "ativo",
                "fonte":          "CEDAMIA",
                "tipo_evidencia": "declaracao-formal",
                "cor_mapa":       cor,
                "url_documento":  c8,
                "url_referencia": c9,
                "observacoes":    c7,
                "verificado":     False,
            })
            rows.append(r)

    print(f"    {len(rows)} jurisdições encontradas")
    return rows


# ── 2. Parser almost-CEDs (xlsx) ──────────────────────────────────────────────

def parse_almost_ced(xlsx_path: Path) -> list[dict]:
    print(f"\n[2] Parseando almost-CEDs: {xlsx_path.name}")
    try:
        xl = pd.ExcelFile(xlsx_path, engine="openpyxl")
    except Exception as e:
        print(f"    [ERRO] Não foi possível abrir o arquivo: {e}")
        return []

    print(f"    Abas encontradas: {xl.sheet_names}")

    sheet_name = next((s for s in xl.sheet_names if "almost" in s.lower()), None)
    if sheet_name is None:
        print("    [AVISO] Aba 'almost-CEDs' não encontrada. Pulando.")
        return []

    df = xl.parse(sheet_name, header=None, dtype=str)
    print(f"    Aba '{sheet_name}': {len(df)} linhas × {len(df.columns)} colunas")
    print("    Primeiras 15 linhas (diagnóstico):")
    print(df.head(15).to_string(max_colwidth=60))
    print()

    # ── Parser adaptativo ────────────────────────────────────────────────────
    # Localizar a linha de cabeçalho: procura por 'country' ou 'jurisdiction'
    header_row = None
    for i in range(min(10, len(df))):
        row_lower = " ".join(str(v).lower() for v in df.iloc[i] if pd.notna(v))
        if "country" in row_lower or "jurisdiction" in row_lower:
            header_row = i
            break

    if header_row is None:
        print("    [AVISO] Cabeçalho não identificado automaticamente.")
        print("    Execute o script para ver o diagnóstico acima e abra um issue.")
        return []

    # Recarregar com cabeçalho correto
    df = xl.parse(sheet_name, header=header_row, dtype=str)
    df.columns = [str(c).strip().lower() for c in df.columns]
    print(f"    Colunas detectadas: {list(df.columns)}")

    col_country = _find_col(df, ["country"])
    col_juris   = _find_col(df, ["government", "jurisdiction", "entity", "council"])
    col_date    = _find_col(df, ["date"])
    col_url     = _find_col(df, ["reference", "url", "link", "minutes", "motion"])
    col_notes   = _find_col(df, ["reason", "notes", "justification", "comment"])

    rows: list[dict] = []
    current_country = ""

    for _, row in df.iterrows():
        raw_country = _s(row.get(col_country, "")) if col_country else ""
        juris       = _s(row.get(col_juris, ""))   if col_juris  else ""
        date        = _s(row.get(col_date, ""))     if col_date   else ""
        url         = _s(row.get(col_url, ""))      if col_url    else ""
        notes       = _s(row.get(col_notes, ""))    if col_notes  else ""

        # Carry-forward de país: linhas de país têm governo vazio
        if raw_country:
            current_country = raw_country
        if not juris:
            continue  # linha de cabeçalho de país sem jurisdição específica

        iso3 = (
            COUNTRY_TO_ISO3.get(current_country)
            or ALMOST_COUNTRY_MAP.get(current_country)
            or ""
        )
        is_crisis = "crisis" in notes.lower()
        r = blank_row()
        r.update({
            "pais":           ISO3_TO_PT.get(iso3, current_country),
            "iso_3":          iso3,
            "nivel":          "estadual" if is_state_level(juris) else "municipal",
            "entidade":       juris,
            "regiao":         "",
            "ano":            extract_year(date),
            "data_completa":  date,
            "status":         "quase",
            "fonte":          "ALMOST-CED",
            "tipo_evidencia": "linguagem-diferente" if is_crisis else "mocao-rejeitada",
            "cor_mapa":       "roxo",
            "url_documento":  url,
            "justificativa":  notes,
            "verificado":     False,
        })
        rows.append(r)

    print(f"    {len(rows)} almost-CEDs encontrados")
    return rows


def _find_col(df: pd.DataFrame, keywords: list[str]) -> str | None:
    for col in df.columns:
        if any(kw in col for kw in keywords):
            return col
    return None


# ── 3. Parser WWA Markdown ────────────────────────────────────────────────────

def parse_wwa(md_path: Path) -> list[dict]:
    print(f"\n[3] Parseando WWA: {md_path.name}")
    text = md_path.read_text(encoding="utf-8")
    rows: list[dict] = []
    seen_iso: set[str] = set()

    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 8:
            continue
        if not parts[1].strip().isdigit():
            continue

        pais_raw = re.sub(r"\*+", "", parts[2]).strip()
        iso3     = parts[3].strip()
        evento   = parts[4].strip()
        ano_str  = parts[5].strip()
        fator    = parts[6].strip()
        url      = parts[7].strip()

        if not re.match(r"^[A-Z]{3}$", iso3):
            continue
        if iso3 in NATIONAL_ISO:
            continue  # já tem CED formal (vermelho) — não duplicar aqui
        if iso3 in seen_iso:
            continue  # primeiro estudo por país
        seen_iso.add(iso3)

        r = blank_row()
        r.update({
            "pais":           ISO3_TO_PT.get(iso3, pais_raw),
            "iso_3":          iso3,
            "nivel":          "nacional",
            "entidade":       pais_raw,
            "regiao":         "",
            "ano":            extract_year(ano_str),
            "data_completa":  ano_str,
            "status":         "atribuicao",
            "fonte":          "WWA",
            "tipo_evidencia": "estudo-atribuicao",
            "cor_mapa":       "azul",
            "url_documento":  url,
            "url_referencia": "https://www.worldweatherattribution.org",
            "fator_risco_wwa": fator,
            "observacoes":    evento,
            "verificado":     True,
        })
        rows.append(r)

    print(f"    {len(rows)} países (deduplicado por ISO, excluindo com CED nacional)")
    return rows


# ── 4. Entradas manuais ───────────────────────────────────────────────────────

def parse_manual() -> list[dict]:
    print("\n[4] Entradas manuais (DECLARAÇÕES_POSTERIORES_2022-2026 + nacionais ausentes do CEDAMIA)")
    entries = [
        # ── Declarações estaduais 2022-2026 ──────────────────────────────────
        {
            "pais":           "Austrália",
            "iso_3":          "AUS",
            "nivel":          "estadual",
            "entidade":       "South Australia Parliament",
            "regiao":         "SA",
            "ano":            2022,
            "data_completa":  "31 May 2022",
            "status":         "ativo",
            "fonte":          "MANUAL",
            "tipo_evidencia": "declaracao-formal",
            "cor_mapa":       "laranja",
            "url_documento":  "https://climateemergencydeclaration.org/first-australian-state-parliament-declares-a-climate-emergency/",
            "url_referencia": "https://anmfsa.org.au/Web/News/2022/Climate%20emergency%20declaration%20passes%20in%20Parliament.aspx",
            "observacoes":    "Primeiro parlamento estadual australiano a declarar emergência climática. Ambas as câmaras aprovaram.",
            "verificado":     True,
        },
        # ── Parlamentos nacionais ausentes do CSV CEDAMIA ────────────────────
        # (o CEDAMIA lista apenas declarações sub-nacionais para esses países)
        {
            "pais":           "Reino Unido",
            "iso_3":          "GBR",
            "nivel":          "nacional",
            "entidade":       "UK Parliament",
            "regiao":         "",
            "ano":            2019,
            "data_completa":  "1 May 2019",
            "status":         "ativo",
            "fonte":          "MANUAL",
            "tipo_evidencia": "declaracao-formal",
            "cor_mapa":       "vermelho",
            "url_documento":  "https://www.parliament.uk/business/news/2019/may/mps-declare-first-ever-climate-emergency/",
            "url_referencia": "https://www.bbc.com/news/uk-politics-48126677",
            "observacoes":    "Moção apresentada por Jeremy Corbyn, aprovada por consenso em 01/05/2019.",
            "verificado":     True,
        },
        {
            "pais":           "Irlanda",
            "iso_3":          "IRL",
            "nivel":          "nacional",
            "entidade":       "Dáil Éireann (Irish Parliament)",
            "regiao":         "",
            "ano":            2019,
            "data_completa":  "9 May 2019",
            "status":         "ativo",
            "fonte":          "MANUAL",
            "tipo_evidencia": "declaracao-formal",
            "cor_mapa":       "vermelho",
            "url_documento":  "https://www.oireachtas.ie/en/debates/debate/dail/2019-05-09/",
            "url_referencia": "https://www.irishtimes.com/news/environment/ireland-declares-climate-and-biodiversity-emergency-1.3894808",
            "observacoes":    "Moção all-party aprovada no Dáil Éireann em 09/05/2019.",
            "verificado":     True,
        },
        {
            "pais":           "Canadá",
            "iso_3":          "CAN",
            "nivel":          "nacional",
            "entidade":       "Parliament of Canada (House of Commons)",
            "regiao":         "",
            "ano":            2019,
            "data_completa":  "17 Jun 2019",
            "status":         "ativo",
            "fonte":          "MANUAL",
            "tipo_evidencia": "declaracao-formal",
            "cor_mapa":       "vermelho",
            "url_documento":  "https://www.ourcommons.ca/DocumentViewer/en/42-1/house/sitting-445/hansard",
            "url_referencia": "https://www.cbc.ca/news/politics/canada-climate-emergency-motion-1.5177299",
            "observacoes":    "Moção aprovada pela Câmara dos Comuns em 17/06/2019, com o governo reconhecendo emergência climática.",
            "verificado":     True,
        },
        {
            "pais":           "Maurícia",
            "iso_3":          "MUS",
            "nivel":          "nacional",
            "entidade":       "National Assembly of Mauritius",
            "regiao":         "",
            "ano":            2021,
            "data_completa":  "2021",
            "status":         "ativo",
            "fonte":          "MANUAL",
            "tipo_evidencia": "declaracao-formal",
            "cor_mapa":       "vermelho",
            "url_documento":  "",
            "url_referencia": "https://cedamia.org",
            "observacoes":    "Declaração nacional registrada pela CEDAMIA. Data exata a verificar.",
            "verificado":     False,
        },
        {
            "pais":           "Vaticano",
            "iso_3":          "VAT",
            "nivel":          "nacional",
            "entidade":       "Holy See",
            "regiao":         "",
            "ano":            2019,
            "data_completa":  "2019",
            "status":         "ativo",
            "fonte":          "MANUAL",
            "tipo_evidencia": "declaracao-formal",
            "cor_mapa":       "vermelho",
            "url_documento":  "",
            "url_referencia": "https://cedamia.org",
            "observacoes":    "Santa Sé reconheceu emergência climática. Data exata a verificar.",
            "verificado":     False,
        },
        {
            "pais":           "Jersey",
            "iso_3":          "JEY",
            "nivel":          "nacional",
            "entidade":       "States of Jersey",
            "regiao":         "",
            "ano":            2019,
            "data_completa":  "2019",
            "status":         "ativo",
            "fonte":          "MANUAL",
            "tipo_evidencia": "declaracao-formal",
            "cor_mapa":       "vermelho",
            "url_documento":  "",
            "url_referencia": "https://cedamia.org",
            "observacoes":    "Dependência britânica com declaração própria. Data exata a verificar.",
            "verificado":     False,
        },
        {
            "pais":           "Gibraltar",
            "iso_3":          "GIB",
            "nivel":          "nacional",
            "entidade":       "Gibraltar Parliament",
            "regiao":         "",
            "ano":            2019,
            "data_completa":  "2019",
            "status":         "ativo",
            "fonte":          "MANUAL",
            "tipo_evidencia": "declaracao-formal",
            "cor_mapa":       "vermelho",
            "url_documento":  "",
            "url_referencia": "https://cedamia.org",
            "observacoes":    "Território britânico ultramarino com declaração própria. Data exata a verificar.",
            "verificado":     False,
        },
        {
            "pais":           "Ilha de Man",
            "iso_3":          "IMN",
            "nivel":          "nacional",
            "entidade":       "Tynwald (Parliament of the Isle of Man)",
            "regiao":         "",
            "ano":            2019,
            "data_completa":  "2019",
            "status":         "ativo",
            "fonte":          "MANUAL",
            "tipo_evidencia": "declaracao-formal",
            "cor_mapa":       "vermelho",
            "url_documento":  "",
            "url_referencia": "https://cedamia.org",
            "observacoes":    "Dependência britânica com parlamento próprio (Tynwald). Data exata a verificar.",
            "verificado":     False,
        },
        # ── "Pending ratification" — não contam como declarações formais ─────
        # (estavam na seção 'Significant declarations' do CEDAMIA, excluídas do CSV principal)
        {
            "pais":           "México",
            "iso_3":          "MEX",
            "nivel":          "nacional",
            "entidade":       "Mexico Senate",
            "regiao":         "",
            "ano":            2019,
            "data_completa":  "3 Sep 2019",
            "status":         "quase",
            "fonte":          "CEDAMIA",
            "tipo_evidencia": "declaracao-formal",
            "cor_mapa":       "vermelho",
            "url_documento":  "https://www.meteored.mx/noticias/actualidad/mexico-se-declara-en-emergencia-climatica.html",
            "observacoes":    "CEDAMIA classifica como 'requiring ratification'. Senado aprovou mas não ratificado pelo Congresso completo.",
            "verificado":     False,
        },
        {
            "pais":           "Portugal",
            "iso_3":          "PRT",
            "nivel":          "nacional",
            "entidade":       "Portugal Assembly of the Republic",
            "regiao":         "",
            "ano":            2019,
            "data_completa":  "7 Jun 2019",
            "status":         "ativo",
            "fonte":          "CEDAMIA",
            "tipo_evidencia": "declaracao-formal",
            "cor_mapa":       "vermelho",
            "url_documento":  "https://www.parlamento.pt/",
            "observacoes":    "Declaração aprovada pela Assembleia da República em 07/06/2019.",
            "verificado":     True,
        },
    ]
    # Preencher colunas ausentes com "" para conformidade de schema
    result = []
    for e in entries:
        r = blank_row()
        r.update(e)
        result.append(r)
    print(f"    {len(result)} entradas")
    return result


# ── Phase 2: join com Natural Earth admin-1 ──────────────────────────────────

def join_adm1(df: pd.DataFrame) -> pd.DataFrame:
    """
    Para cada entrada de nível estadual ou municipal, tenta casar o campo
    `regiao` (e como fallback `entidade`) com o nome de uma unidade
    Natural Earth admin-1 do mesmo país (adm0_a3 == iso_3).

    Resultado: coluna `adm1_ne_id` com o ne_id inteiro da NE (ou None).
    Fonte preferida: ne_50m_admin1_slim.geojson (já gerado pelo setup.py).
    """
    import json

    try:
        from rapidfuzz import process, fuzz
    except ImportError:
        print("\n    [AVISO] rapidfuzz não instalado. Pulando join admin-1.")
        print("    Para instalar: pip install rapidfuzz")
        df["adm1_ne_id"] = None
        return df

    geo_path = None
    for candidate in [
        PWA_DATA / "ne_50m_admin1_slim.geojson",
        PWA_DATA / "ne_50m_admin1.geojson",
    ]:
        if candidate.exists():
            geo_path = candidate
            break

    if geo_path is None:
        print("\n    [AVISO] ne_50m_admin1_slim.geojson não encontrado.")
        print("    Execute 'python ced-map-pwa/setup.py' primeiro para baixar o GeoJSON.")
        df["adm1_ne_id"] = None
        return df

    print(f"\n[5] Join admin-1 com {geo_path.name}...", end=" ", flush=True)

    with open(geo_path, encoding="utf-8") as f:
        gj = json.load(f)

    # Indexar features por adm0_a3 → lista de {ne_id, name, iso_suffix}
    # iso_suffix: parte após o "-" em iso_3166_2 (ex.: "AU-NSW" → "NSW")
    ne_idx: dict[str, list[dict]] = {}
    for feat in gj["features"]:
        props = feat.get("properties") or {}
        iso   = (props.get("adm0_a3") or "").strip().upper()
        ne_id = props.get("ne_id")
        name  = (props.get("name") or "").strip()
        iso2  = (props.get("iso_3166_2") or "")
        # Extrair sufixo após "-" (ex.: "AU-NSW" → "NSW"; "AU-X02~" → "X02~")
        iso_suffix = iso2.split("-", 1)[1].upper() if "-" in iso2 else ""
        if iso and ne_id and name:
            ne_idx.setdefault(iso, []).append({
                "ne_id":      int(ne_id),
                "name":       name,
                "iso_suffix": iso_suffix,
            })

    SCORE_THRESHOLD = 75  # mínimo de similaridade (0-100) para aceitar o match

    def find_ne_id(row) -> int | None:
        if row["nivel"] == "nacional":
            return None  # países não têm geometria admin-1

        iso3 = str(row.get("iso_3", "")).strip().upper()
        candidates = ne_idx.get(iso3, [])
        if not candidates:
            return None

        # 1. Tentativa de match exato contra iso_suffix (cobre abreviações tipo NSW, QLD)
        for query_field in [row.get("regiao", ""), row.get("entidade", "")]:
            q = str(query_field or "").strip().upper()
            if not q or len(q) < 2:
                continue
            for c in candidates:
                if c["iso_suffix"] and c["iso_suffix"] == q:
                    return c["ne_id"]

        # 2. Fuzzy match contra nome completo
        names = [c["name"] for c in candidates]
        for query in [row.get("regiao", ""), row.get("entidade", "")]:
            query = str(query or "").strip()
            if not query or len(query) < 3:
                continue
            result = process.extractOne(
                query, names,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=SCORE_THRESHOLD,
            )
            if result:
                matched_name, score, idx = result
                return candidates[idx]["ne_id"]

        return None

    df["adm1_ne_id"] = df.apply(find_ne_id, axis=1)

    matched   = df["adm1_ne_id"].notna().sum()
    sub_total = (df["nivel"] != "nacional").sum()
    print(f"{matched}/{sub_total} jurisdições sub-nacionais casadas com polígono admin-1")

    return df


# ── Build principal ───────────────────────────────────────────────────────────

def build():
    print("=" * 60)
    print("BUILD BANCO UNIFICADO CED")
    print("=" * 60)

    cedamia_rows = parse_cedamia(BASE / "cedamia_data.csv")
    almost_rows  = parse_almost_ced(BASE / "Climate Emergency Declaration (CED) data sheet.xlsx")
    wwa_rows     = parse_wwa(BASE / "ATRIBUICAO_CLIMATICA_WWA.md")
    manual_rows  = parse_manual()

    all_rows = cedamia_rows + almost_rows + wwa_rows + manual_rows

    df = pd.DataFrame(all_rows, columns=SCHEMA_COLS)

    # ── Deduplicação por (iso_3 + entidade + ano + fonte) ────────────────────
    before = len(df)
    df = df.drop_duplicates(subset=["iso_3", "entidade", "ano", "fonte"], keep="first")
    df.insert(0, "id", range(1, len(df) + 1))
    after = len(df)
    removed = before - after
    if removed:
        print(f"\n    Deduplicação: {removed} linhas removidas")

    # ── Phase 2: Join com Natural Earth admin-1 ───────────────────────────────
    df = join_adm1(df)

    # ── Sumário ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMÁRIO DO BANCO UNIFICADO")
    print("=" * 60)
    print(f"Total de entradas: {len(df)}")
    print("\nPor fonte:")
    print(df["fonte"].value_counts().to_string())
    print("\nPor nível:")
    print(df["nivel"].value_counts().to_string())
    print("\nPor cor_mapa:")
    print(df["cor_mapa"].value_counts().to_string())
    print("\nPaíses distintos (iso_3):", df["iso_3"].nunique())

    # ── Exportar ──────────────────────────────────────────────────────────────
    out_csv  = BASE / "BANCO_UNIFICADO_CED.csv"
    out_xlsx = BASE / "BANCO_UNIFICADO_CED.xlsx"

    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    df.to_excel(out_xlsx, index=False, sheet_name="BANCO_UNIFICADO")

    print(f"\nSalvo: {out_csv}")
    print(f"Salvo: {out_xlsx}")
    print("\nConcluído!")


if __name__ == "__main__":
    build()
