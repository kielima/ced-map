---
titulo: PLANO DESENVOLVIMENTO V4
descricao: Plano técnico do CED Map — banco unificado + PWA interativa
tags: [academico-e-pesquisa, emergencia-climatica]
status: em-andamento
ultima_atualizacao: 2026-05-14
---

# CED Map — Plano Técnico v4

**Objetivo:** construir uma PWA interativa que mapeia globalmente declarações de emergência climática (CED), atribuição científica (WWA) e quase-declarações (almost-CED), com zoom até nível municipal e filtros dinâmicos.

**Repositório alvo:** `ced-map` no GitHub Pages  
**Responsável:** Kiê (kly@sapo.pt)

---

## Fase 1 — Banco de Dados Unificado 🔴 FAZER AGORA

### Objetivo
Criar `BANCO_UNIFICADO_CED.csv` como única fonte de verdade para o app, consolidando todas as camadas de dados com rastreamento de origem por linha.

### Script a criar: `build_banco_unificado.py`

**Entradas:**

| # | Arquivo | Camada | `fonte=` |
|---|---------|--------|----------|
| 1 | `cedamia_data.csv` | CED formais (nacional + estadual + municipal) | `CEDAMIA` |
| 2 | `ATRIBUICAO_CLIMATICA_WWA.md` | Atribuição climática científica | `WWA` |
| 3 | `Climate Emergency Declaration (CED) data sheet.xlsx` → aba `almost-CEDs` | Tentativas rejeitadas/linguagem divergente | `ALMOST-CED` |
| 4 | `DECLARAÇÕES_POSTERIORES_2022-2026.md` | Declarações recentes não em CEDAMIA | `MANUAL` |

**Saídas:**
- `BANCO_UNIFICADO_CED.csv` — usado pelo script do mapa e pela PWA
- `BANCO_UNIFICADO_CED.xlsx` — para inspeção manual

### Schema do banco

| Coluna | Tipo | Valores possíveis | Obrigatório |
|--------|------|-------------------|-------------|
| `id` | int | sequencial | ✅ |
| `pais` | str | nome em português | ✅ |
| `iso_3` | str | ISO 3166-1 alpha-3 | ✅ |
| `nivel` | str | `nacional` / `estadual` / `municipal` / `parlamentar` | ✅ |
| `entidade` | str | nome da jurisdição | ✅ |
| `regiao` | str | estado/província, se aplicável | — |
| `ano` | int | 2016–2026 | ✅ |
| `data_completa` | date | YYYY-MM-DD se conhecida | — |
| `status` | str | `ativo` / `rejeitado` / `quase` / `atribuicao` | ✅ |
| `fonte` | str | `CEDAMIA` / `WWA` / `ALMOST-CED` / `MANUAL` | ✅ |
| `tipo_evidencia` | str | `declaracao-formal` / `estudo-atribuicao` / `mocao-rejeitada` / `linguagem-diferente` / `emenda-removeu-ce` | ✅ |
| `cor_mapa` | str | `vermelho` / `laranja` / `amarelo` / `azul` / `roxo` / `cinza` | ✅ |
| `url_documento` | str | link para documento oficial | — |
| `url_referencia` | str | link para fonte secundária | — |
| `fator_risco_wwa` | str | ex.: "30x mais provável" (só para WWA) | — |
| `justificativa` | str | motivo da exclusão (só para almost-CED) | — |
| `observacoes` | str | notas adicionais | — |
| `verificado` | bool | TRUE / FALSE | ✅ |

### Regra de deduplicação
Chave única: `(iso_3, entidade, ano)` — se o mesmo registro aparecer em mais de uma fonte, manter o de maior confiança: `CEDAMIA > MANUAL > ALMOST-CED > WWA`.

### Regra de `cor_mapa`
```python
def atribuir_cor(row):
    if row['fonte'] == 'WWA':
        return 'azul'
    if row['fonte'] == 'ALMOST-CED':
        return 'roxo'
    if row['nivel'] == 'nacional':
        return 'vermelho'
    if row['nivel'] in ('estadual', 'parlamentar'):
        return 'laranja'
    return 'amarelo'  # municipal / local
```

### Checklist Fase 1
- [ ] Parsear `cedamia_data.csv` → colunas padronizadas
- [ ] Parsear aba `almost-CEDs` da planilha CEDAMIA
- [ ] Incorporar 26 países de `ATRIBUICAO_CLIMATICA_WWA.md`
- [ ] Incorporar entradas de `DECLARAÇÕES_POSTERIORES_2022-2026.md`
- [ ] Deduplicar por chave `(iso_3, entidade, ano)`
- [ ] Atribuir `cor_mapa` automaticamente
- [ ] Exportar `BANCO_UNIFICADO_CED.csv` e `.xlsx`
- [ ] Validar: total de linhas, distribuição por fonte, ISOs inválidos

---

## Fase 2 — PWA Interativa (GitHub Pages) 🔴 FAZER A SEGUIR

### Objetivo
App web instalável com mapa global interativo, zoom até município, filtros dinâmicos.

### Stack

| Componente | Tecnologia |
|-----------|-----------|
| Renderização do mapa | **MapLibre GL JS** (WebGL, open-source, suporta PMTiles) |
| Dados geográficos | **PMTiles** (vector tiles estáticos, sem servidor) |
| Dados de atributos | `banco_unificado.json` (< 2 MB, gerado a partir do CSV) |
| Hosting | **GitHub Pages** |
| PWA | `manifest.json` + Service Worker (`sw.js`) |
| UI / Filtros | Vanilla JS |
| Estilo | CSS puro, responsivo |

### Dados geográficos por nível de zoom

| Nível | Fonte | Zoom ativo |
|-------|-------|-----------|
| Admin-0 (países) | Natural Earth 110m → PMTiles | 2–4 |
| Admin-1 (estados/províncias) | Natural Earth 10m → PMTiles | 5–7 |
| Admin-2 (municípios) | **GADM v4.1** (gadm.org, uso acadêmico gratuito) → PMTiles | 8–12 |

**Ferramentas de pré-processamento:**
- `tippecanoe` — converte GeoJSON → PMTiles com simplificação por zoom
- Hospedar `.pmtiles` no GitHub Releases (sem limite de tamanho)

### Estrutura do repositório

```
ced-map/
├── index.html              ← entry point da PWA
├── manifest.json           ← ícone, nome, cor de tema
├── sw.js                   ← Service Worker (cache offline)
├── app.js                  ← MapLibre: init, camadas, filtros
├── style.css               ← layout responsivo
├── data/
│   └── banco_unificado.json  ← atributos de todas as jurisdições
└── tiles/                  ← ou link para GitHub Releases
    ├── admin0.pmtiles
    ├── admin1.pmtiles
    └── admin2.pmtiles
```

### Filtros da interface

| Filtro | Tipo | Valores |
|--------|------|---------|
| Nível | Checkbox múltiplo | Nacional / Estadual / Municipal |
| Camada | Checkbox múltiplo | CED Formal / Atribuição WWA / Almost-CED |
| Status | Checkbox múltiplo | Ativo / Rejeitado / Quase |
| Ano | Slider duplo | 2016 – 2026 |
| País | Dropdown com busca | lista de ISOs |

### Legenda

| Cor | Hex | Categoria |
|-----|-----|-----------|
| 🔴 Vermelho | `#C0392B` | Declaração nacional / parlamentar |
| 🟠 Laranja | `#E67E22` | Estado / província declarante |
| 🟡 Amarelo | `#F4D03F` | Município / jurisdição local |
| 🔵 Azul-aço | `#5B8DB8` | Evento atribuído às MC (WWA) |
| 🟣 Roxo | `#8E44AD` | Declaração tentada e rejeitada / linguagem divergente |
| ⬜ Cinza | `#D9D9D9` | Sem registro |

### Comportamento por zoom
- **Zoom 2–4:** polígonos de país coloridos pela camada mais alta (vermelho > laranja > amarelo > azul > roxo)
- **Zoom 5–7:** polígonos admin-1 (estados/províncias) com cor própria; países sem admin-1 colorido mantêm cor do país
- **Zoom 8–12:** polígonos admin-2 (municípios) com cor própria; ao clicar abre painel com nome, data, fonte e link

### Checklist Fase 2
- [ ] Criar repositório `ced-map` no GitHub
- [ ] Baixar GADM v4.1 para países com alta densidade de CEDs (AUS, UK, USA, DEU, CAN, IRL, NZL)
- [ ] Processar GeoJSONs com `tippecanoe` → `.pmtiles`
- [ ] Implementar `app.js` com MapLibre + camadas por zoom
- [ ] Implementar filtros (checkbox + slider)
- [ ] Conectar `banco_unificado.json` às camadas do mapa
- [ ] Configurar GitHub Pages + Service Worker
- [ ] Testar em mobile e desktop

---

## Fase 3 — Melhorias iterativas (depois do MVP)

- [ ] Painel lateral com ficha do país/jurisdição ao clicar
- [ ] URL com estado dos filtros (para compartilhar links)
- [ ] Modo escuro
- [ ] Exportar seleção como CSV
- [ ] Internacionalização (PT/EN)
- [ ] Cobertura GADM para todos os países (não só os de alta densidade)

---

## Decisões em aberto

| Decisão | Opções | Status |
|---------|--------|--------|
| Repositório GitHub | Novo repo `ced-map` vs. subpasta de repositório existente | ⏳ pendente |
| Granulometria inicial da Fase 2 | Todos os países vs. só países com alta densidade de CEDs | ⏳ pendente |
| almost-CED no nível municipal | Incluir só países-cinza (MHL, LUX) vs. todos os municípios rejeitados | ⏳ pendente |

---

*Atualizado em 2026-05-14. Fase 1 é a próxima ação — criar `build_banco_unificado.py`.*
