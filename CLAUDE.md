# CED Map — Contexto para o Claude

Leia este arquivo antes de qualquer outra coisa. Ele descreve o projeto, o estado atual e o que fazer a seguir.

---

## O que é este projeto

**CED Map** é uma PWA (Progressive Web App) interativa hospedada em GitHub Pages que mapeia globalmente:

1. **Declarações formais de emergência climática (CED)** — governos que aprovaram legislação ou moção formal, em nível nacional, estadual/provincial e municipal. Fonte: CEDAMIA (cedamia.org).
2. **Atribuição climática documentada (WWA)** — países com desastres atribuídos cientificamente às mudanças climáticas pelo World Weather Attribution.
3. **Quase-declarações (almost-CEDs)** — tentativas rejeitadas ou com linguagem divergente.

**URL em produção:** `https://kielima.github.io/ced-map/`  
**Repo GitHub:** `https://github.com/kielima/ced-map`

---

## Estrutura do repositório

```
ced-map/                          ← raiz do repo (= ced-map-pwa/)
├── build/                        ← pipeline de dados
│   ├── build_banco_unificado.py  ← consolida 4 fontes → BANCO_UNIFICADO_CED.csv
│   ├── geocode_banco.py          ← batch geocoder Nominatim → build/geocodes.json (Fase 3)
│   ├── build_admin2_polygons.py  ← GADM v4.1 admin-2 → data/admin2_top5.geojson (Fase 3)
│   ├── cedamia_data.csv          ← 2.163 linhas, todas as jurisdições CED mundiais
│   ├── ATRIBUICAO_CLIMATICA_WWA.md  ← 26 países WWA com links dos estudos
│   ├── DECLARAÇÕES_POSTERIORES_2022-2026.md ← declarações recentes manuais
│   ├── Climate Emergency Declaration (CED) data sheet.xlsx ← planilha oficial CEDAMIA
│   ├── PLANO_DESENVOLVIMENTO_V4.md ← plano técnico completo das fases
│   ├── BANCO_UNIFICADO_CED.csv   ← saída gerada (não editar manualmente)
│   ├── BANCO_UNIFICADO_CED.xlsx  ← saída gerada (para inspeção)
│   ├── geocodes.json             ← cache do geocoder (gitignored, gerado por geocode_banco.py)
│   └── _downloads/               ← cache GADM v4.1 (gitignored)
├── data/                         ← dados servidos pela PWA
│   ├── banco.json                ← banco compilado para o front-end
│   ├── ne_110m_countries.geojson ← países Natural Earth 110m
│   ├── ne_50m_admin1_slim.geojson ← estados/províncias Natural Earth 50m (slim)
│   └── admin2_top5.geojson       ← municípios/condados top-5 (Fase 3, gerado)
├── js/
│   └── app.js                    ← lógica principal da PWA (MapLibre + filtros)
├── index.html                    ← shell da PWA
├── style.css                     ← estilos
├── manifest.json                 ← manifesto PWA
├── sw.js                         ← service worker (cache-first)
├── setup.py                      ← baixa GeoJSON + converte CSV → banco.json
└── CLAUDE.md                     ← este arquivo
```

---

## Esquema de cores

| Cor | Hex | Significado |
|-----|-----|-------------|
| Vermelho | `#C0392B` | Declaração nacional/parlamentar |
| Laranja | `#E67E22` | Declaração estadual/provincial |
| Amarelo | `#F4D03F` | Declaração municipal/local |
| Azul-aço | `#5B8DB8` | Atribuição climática WWA |
| Roxo | `#8E44AD` | Tentativa rejeitada / quase-CED |
| Cinza | `#D9D9D9` | Sem registro |

---

## Fases de desenvolvimento

| Fase | Status | Descrição |
|------|--------|-----------|
| **Fase 1** | ✅ Concluída | PWA MVP com camada de países (admin-0), filtros dinâmicos, info panel, deploy GitHub Pages |
| **Fase 2** | ✅ Concluída | Camada admin-1 (estados/províncias) com Natural Earth 50m + join rapidfuzz (`adm1_ne_id`) |
| **Fase 3** | 🟡 Em andamento | Scripts e UI prontos. Pendente: rodar `geocode_banco.py` (Nominatim, ~22 min) e `build_admin2_polygons.py` (GADM v4.1, top-5) para gerar os dados. |
| **Fase 4** | 🔴 Futura | Painel de estatísticas/charts (tendência temporal, ranking de países) |

---

## Como rodar o pipeline de build

### Pré-requisitos
```bash
pip install pandas openpyxl rapidfuzz requests
```

### Fluxo completo (rebuild do zero)
```bash
# 1. Baixar GeoJSONs e criar slim do admin-1
python setup.py

# 2. Reconstruir banco unificado com join admin-1
python build/build_banco_unificado.py

# 3. Converter banco.csv → banco.json (para a PWA)
python setup.py

# 4. Testar localmente
python setup.py serve
# Acesse: http://localhost:8080
```

### Apenas atualizar o banco (sem re-download de GeoJSON)
```bash
python build/build_banco_unificado.py && python setup.py
```

---

## Estado atual do banco (mai/2026)

- **1.973 entradas** totais
- **74 países** distintos
- **1.204/1.285** jurisdições sub-nacionais com ISO casadas com Natural Earth admin-1 (**93.7%**)
- Fontes: CEDAMIA (1.847) · ALMOST-CED (91) · WWA (26) · MANUAL (9)
- Níveis: municipal (1.868) · estadual (53) · nacional (52)

---

## Schema do banco (`build/BANCO_UNIFICADO_CED.csv`)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | int | ID sequencial |
| `pais` | str | Nome do país em português |
| `iso_3` | str | ISO Alpha-3 do país |
| `nivel` | str | `nacional` / `estadual` / `municipal` |
| `entidade` | str | Nome da entidade declarante |
| `regiao` | str | Estado/província (quando aplicável) |
| `ano` | int | Ano da declaração |
| `data_completa` | str | Data completa (formato variável) |
| `status` | str | `ativo` / `atribuicao` / `quase` |
| `fonte` | str | `CEDAMIA` / `WWA` / `ALMOST-CED` / `MANUAL` |
| `tipo_evidencia` | str | `declaracao-formal` / `estudo-atribuicao` / etc. |
| `cor_mapa` | str | `vermelho` / `laranja` / `amarelo` / `azul` / `roxo` |
| `url_documento` | str | URL do documento original |
| `url_referencia` | str | URL de referência/mídia |
| `fator_risco_wwa` | str | Fator de risco climático (só WWA) |
| `justificativa` | str | Motivo de rejeição (só almost-CED) |
| `observacoes` | str | Notas adicionais |
| `verificado` | bool | Se foi verificado manualmente |
| `adm1_ne_id` | int | ID Natural Earth admin-1 (join para polígono estadual) |
| `lat` | float | Latitude geocodificada via Nominatim (Fase 3) — só sub-nacionais |
| `lon` | float | Longitude geocodificada via Nominatim (Fase 3) — só sub-nacionais |

---

## Fase 3 — Camada municipal

### Estado
- ✅ `build/geocode_banco.py` — batch geocoder Nominatim com cache resumível (`build/geocodes.json`)
- ✅ `build/build_admin2_polygons.py` — baixa GADM v4.1 admin-2 dos top-5 países, simplifica e gera `data/admin2_top5.geojson`
- ✅ Schema do banco com `lat`/`lon` (gera silenciosamente sem cache; injeta coordenadas quando o cache existe)
- ✅ `js/app.js` (v5) — clustering MapLibre nativo para pontos + admin-2 lazy-load em zoom ≥ 6
- ⏳ Rodar o geocoder com internet (`python build/geocode_banco.py`) — ~22 min para os 1.285 alvos
- ⏳ Rodar o builder admin-2 (`python build/build_admin2_polygons.py`) — baixa ~5 países do GADM v4.1
- ⏳ Re-executar `build/build_banco_unificado.py` + `setup.py` para regenerar `banco.json` com lat/lon

### Como rodar a Fase 3 completa
```bash
# 1. Geocodificar (pode interromper com Ctrl+C e retomar; cache é incremental)
pip install requests shapely
python build/geocode_banco.py             # leva ~22 min na primeira vez
python build/geocode_banco.py --retry-failed   # se algumas falharem

# 2. Baixar e simplificar GADM admin-2 dos top-5 países
python build/build_admin2_polygons.py     # gera data/admin2_top5.geojson

# 3. Regenerar banco com lat/lon
python build/build_banco_unificado.py && python setup.py

# 4. Testar
python setup.py serve
```

### Top países por jurisdição sub-nacional
| Rank | ISO | País | Entradas |
|------|-----|------|---------|
| 1 | EU | União Europeia | 636 |
| 2 | KOR | Coreia do Sul | 229 |
| 3 | USA | Estados Unidos | 218 |
| 4 | CAN | Canadá | 136 |
| 5 | JPN | Japão | 135 |
| 6 | DEU | Alemanha | 126 |
| 7 | AUS | Austrália | 120 |
| 8 | ITA | Itália | 116 |

### Notas sobre PMTiles
A rota PMTiles "puro Python" (sem tippecanoe) exige um encoder MVT correto com
clipping, quantização e simplificação por zoom — é um projeto à parte. A solução
adotada serve o GeoJSON slim direto ao MapLibre (lazy-load em zoom ≥ 6), e o
script `build/build_admin2_polygons.py` documenta o comando `tippecanoe` para
quem quiser converter no Linux/WSL e hospedar em GitHub Releases.

---

## Contexto da pesquisa

Este mapa faz parte de uma dissertação de mestrado (PUC-Campinas) sobre eco-eficiência do concreto UHPC. O sub-projeto "Declaração de Emergência Climática" contextualiza a urgência climática que motiva novas normas construtivas (NBR 17246 / UHPC). Qualificação: 02-jun-2026.

**Autor:** Kiê Tibu  
**Repo:** `kielima/ced-map`
