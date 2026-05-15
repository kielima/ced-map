# 🌍 CED Map — Declarações de Emergência Climática

Mapa interativo global de declarações de emergência climática, atribuição científica (WWA) e tentativas rejeitadas.

**[→ Abrir o mapa](https://kielima.github.io/ced-map/)**

---

## O que mostra

| Cor | Significado |
|-----|-------------|
| 🔴 Vermelho | Declaração formal nacional/parlamentar |
| 🟠 Laranja | Declaração estadual/provincial |
| 🟡 Amarelo | Declaração municipal/local |
| 🔵 Azul-aço | Atribuição climática científica (WWA) |
| 🟣 Roxo | Tentativa rejeitada / linguagem divergente |
| ⬜ Cinza | Sem registro |

---

## Fontes de dados

| Fonte | Conteúdo |
|-------|---------|
| [CEDAMIA](https://cedamia.org) | 2.163 jurisdições com declaração formal (mai/2026) |
| [World Weather Attribution](https://worldweatherattribution.org) | 26 países com atribuição científica peer-reviewed |
| [Natural Earth](https://naturalearthdata.com) | Geometrias de países e estados/províncias |

---

## Estrutura do projeto

```
ced-map/
├── build/                    ← pipeline de dados (rodar localmente)
│   ├── build_banco_unificado.py
│   ├── cedamia_data.csv
│   ├── ATRIBUICAO_CLIMATICA_WWA.md
│   └── ...
├── data/                     ← dados servidos pela PWA
│   ├── banco.json
│   ├── ne_110m_countries.geojson
│   └── ne_50m_admin1_slim.geojson
├── js/app.js                 ← lógica principal
├── index.html
├── setup.py                  ← prepara dados
└── sw.js                     ← service worker
```

---

## Como rodar localmente

### Pré-requisitos
```bash
pip install pandas openpyxl rapidfuzz requests
```

### Iniciar o servidor de desenvolvimento
```bash
python setup.py serve
# Acesse: http://localhost:8080
```

### Rebuild completo dos dados
```bash
python setup.py                          # baixa GeoJSONs
python build/build_banco_unificado.py   # reconstrói banco
python setup.py                          # converte CSV → banco.json
```

---

## Funcionalidades

- 🗺️ **3 camadas hierárquicas**: países (admin-0), estados/províncias (admin-1), municípios (admin-2 top-10) com lazy-load por zoom
- 📍 **1.257 jurisdições geocodificadas** exibidas como pontos com clustering nativo MapLibre
- 🔍 **Filtros dinâmicos**: camada (CED/WWA/quase), nível (nacional/estadual/municipal), período (1990–2026), busca por nome
- 📊 **Painel de estatísticas** com Chart.js (timeline, top países, distribuição por nível)
- 🔗 **Deep linking por URL** — partilhe a vista actual copiando o link
- 💾 **Export CSV** dos dados filtrados
- 🚩 **Reportar inconsistências** — botão em cada entrada abre uma GitHub Issue pré-preenchida
- 🌙 **Dark mode** + 🌐 **i18n** PT/EN
- 📱 **PWA installable** com cache offline (service worker)

## Curadoria

Acesse o **modo curador** com `?admin=1` na URL (ex.: `https://kielima.github.io/ced-map/?admin=1`):
- Filtra automaticamente para mostrar só as 1.942 entradas não-verificadas
- Cada entrada tem botão **✓ Verificar** que abre uma GitHub Issue confirmando a verificação
- Após análise, o mantenedor actualiza `verificado: true` no pipeline e no próximo deploy a entrada some do modo curador

## Estado atual (mai/2026)

- **1.973 jurisdições** · **74 países**
- **1.251/1.285** jurisdições sub-nacionais com lat/lon (97.4%)
- **1.204/1.285** com ISO casado com Natural Earth admin-1 (93.7%)
- Fontes: CEDAMIA (1.847) · ALMOST-CED (91) · WWA (26) · MANUAL (9)

---

## Licença

Código: MIT. Dados: termos das fontes originais (CEDAMIA, WWA, Natural Earth).
