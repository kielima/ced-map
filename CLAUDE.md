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
│   ├── cedamia_data.csv          ← 2.163 linhas, todas as jurisdições CED mundiais
│   ├── ATRIBUICAO_CLIMATICA_WWA.md  ← 26 países WWA com links dos estudos
│   ├── DECLARAÇÕES_POSTERIORES_2022-2026.md ← declarações recentes manuais
│   ├── Climate Emergency Declaration (CED) data sheet.xlsx ← planilha oficial CEDAMIA
│   ├── PLANO_DESENVOLVIMENTO_V4.md ← plano técnico completo das fases
│   ├── BANCO_UNIFICADO_CED.csv   ← saída gerada (não editar manualmente)
│   └── BANCO_UNIFICADO_CED.xlsx  ← saída gerada (para inspeção)
├── data/                         ← dados servidos pela PWA
│   ├── banco.json                ← banco compilado para o front-end
│   ├── ne_110m_countries.geojson ← países Natural Earth 110m
│   └── ne_50m_admin1_slim.geojson ← estados/províncias Natural Earth 50m (slim)
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
| **Fase 3** | 🔴 Próxima | Camada municipal — pontos geocodificados (Nominatim) + PMTiles para top-5 países |
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
- **455/1.921** jurisdições sub-nacionais com `adm1_ne_id` (join com Natural Earth admin-1)
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

---

## Fase 3 — Próxima implementação

### Objetivo
Mostrar pontos (círculos) geocodificados para cada jurisdição no mapa ao zoom ≥ 5.  
Para os top-5 países (KOR, USA, CAN, JPN, DEU) tentar PMTiles com polígonos reais.

### Arquivos a criar
- `build/geocode_banco.py` — batch geocoder via Nominatim (1 req/s), cacheia em `build/geocodes.json`
- Atualizar `build/build_banco_unificado.py` — adicionar colunas `lat` e `lon` ao schema
- Atualizar `setup.py` — converter `lat`/`lon` como floats no banco.json
- Atualizar `js/app.js` (v5) — adicionar layer de círculos com clustering MapLibre ao zoom ≥ 5

### Top países por jurisdição sub-nacional (para priorizar geocoding)
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

### Entidades únicas a geocodificar: ~1.281

### Nota sobre tippecanoe
Tippecanoe não está disponível no Windows sem WSL. Para PMTiles, usar a abordagem
Python: `pip install pmtiles mapbox-vector-tile shapely` (já instalados).

---

## Contexto da pesquisa

Este mapa faz parte de uma dissertação de mestrado (PUC-Campinas) sobre eco-eficiência do concreto UHPC. O sub-projeto "Declaração de Emergência Climática" contextualiza a urgência climática que motiva novas normas construtivas (NBR 17246 / UHPC). Qualificação: 02-jun-2026.

**Autor:** Kiê Tibu  
**Repo:** `kielima/ced-map`
