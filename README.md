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

## Estado atual (mai/2026)

- **1.973 jurisdições** · **74 países**
- Fase 1 ✅ PWA base com filtros e info panel
- Fase 2 ✅ Camada de estados/províncias (Natural Earth 50m)
- Fase 3 🔴 Pontos geocodificados por município (próxima)

---

## Licença

Código: MIT. Dados: termos das fontes originais (CEDAMIA, WWA, Natural Earth).
