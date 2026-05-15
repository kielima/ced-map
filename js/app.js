/**
 * app.js — CED Map PWA
 * Lógica principal: mapa MapLibre, filtros, popup de informação.
 */

// ── Constantes ────────────────────────────────────────────────────────────────

const COLORS = {
  vermelho: '#C0392B',
  laranja:  '#E67E22',
  amarelo:  '#F4D03F',
  azul:     '#5B8DB8',
  roxo:     '#8E44AD',
  cinza:    '#D9D9D9',
};

/** Prioridade de exibição quando um país tem múltiplas categorias ativas */
const COLOR_PRIORITY = ['vermelho', 'laranja', 'amarelo', 'azul', 'roxo'];

/** Mapeamento de layer-toggle → fontes e statuses correspondentes */
const LAYER_MAP = {
  'ced-formal':  { fontes: ['CEDAMIA', 'MANUAL'], status: ['ativo'] },
  'wwa':         { fontes: ['WWA'],                status: ['atribuicao'] },
  'almost-ced':  { fontes: ['ALMOST-CED'],         status: ['quase', 'rejeitado'] },
};

// ── Estado global ─────────────────────────────────────────────────────────────

let banco = [];           // todas as entradas do banco
let map   = null;         // instância MapLibre
let selectedIso = null;   // iso_3 selecionado no info-panel
let activeTab = 'declaracoes'; // tab ativa no info-panel

const filters = {
  layers:   new Set(['ced-formal', 'wwa', 'almost-ced']), // camadas ativas
  niveis:   new Set(['nacional', 'estadual', 'municipal']),
  ano_min:  1990,
  ano_max:  2026,
};

// ── Inicialização ─────────────────────────────────────────────────────────────

async function init() {
  try {
    banco = await loadBanco();
    setupMap();
  } catch (err) {
    console.error('Erro na inicialização:', err);
    document.getElementById('loading').innerHTML =
      `<p style="color:#f87171">Erro ao carregar dados:<br>${err.message}</p>
       <p style="font-size:0.8rem;color:#8a9ab0;margin-top:8px">
         Execute <code>python setup.py</code> para preparar os dados.</p>`;
  }
}

async function loadBanco() {
  const r = await fetch('data/banco.json');
  if (!r.ok) throw new Error(`banco.json não encontrado (${r.status}). Execute setup.py.`);
  return r.json();
}

// ── MapLibre ──────────────────────────────────────────────────────────────────

function setupMap() {
  map = new maplibregl.Map({
    container: 'map',
    style: 'https://tiles.openfreemap.org/styles/liberty',
    center: [10, 20],
    zoom: 2,
    minZoom: 1.5,
    maxZoom: 14,
    attributionControl: false,
  });

  map.addControl(new maplibregl.NavigationControl(), 'top-right');
  map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');

  map.on('load', onMapLoad);
  map.on('error', e => console.warn('MapLibre:', e.error?.message));
}

async function onMapLoad() {
  // Carregar GeoJSON de países (Natural Earth 110m)
  let countriesGeo;
  try {
    const r = await fetch('data/ne_110m_countries.geojson');
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    countriesGeo = await r.json();
  } catch (err) {
    console.warn('GeoJSON de países não encontrado:', err.message);
    console.warn('Execute "python setup.py" para baixar os dados geográficos.');
    hideLoading();
    setupFiltersUI();
    updateStats();
    return;
  }

  // Source: países (admin-0)
  map.addSource('countries', {
    type: 'geojson',
    data: countriesGeo,
    promoteId: 'ADM0_A3',  // usar ISO-A3 como feature ID para setFeatureState
  });

  // Layer: fill de países
  map.addLayer({
    id: 'countries-fill',
    type: 'fill',
    source: 'countries',
    paint: {
      'fill-color': buildCountryColorExpr(),
      'fill-opacity': 0.75,
    },
  }, firstSymbolLayer());

  // Layer: borda de países
  map.addLayer({
    id: 'countries-border',
    type: 'line',
    source: 'countries',
    paint: {
      'line-color': '#ffffff',
      'line-width': 0.4,
      'line-opacity': 0.6,
    },
  }, firstSymbolLayer());

  // Layer: highlight de país selecionado
  map.addLayer({
    id: 'countries-highlight',
    type: 'line',
    source: 'countries',
    paint: {
      'line-color': '#ffffff',
      'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 2.5, 0],
      'line-opacity': 1,
    },
  });

  // Admin-1 (estados/províncias) — Phase 2: requer join regiao→admin1 ID
  // loadAdmin1Layer();  // desabilitado no MVP para evitar freeze com 29MB GeoJSON

  // Interatividade
  map.on('click', 'countries-fill', onCountryClick);
  map.on('mousemove', 'countries-fill', onCountryHover);
  map.on('mouseleave', 'countries-fill', onCountryLeave);

  hideLoading();
  setupFiltersUI();
  updateStats();
}

/** Retorna o id da primeira camada de símbolos (para inserir layers abaixo de labels) */
function firstSymbolLayer() {
  const layers = map.getStyle()?.layers ?? [];
  return layers.find(l => l.type === 'symbol')?.id;
}

/** Tenta carregar admin-1 (states/provinces) se disponível */
async function loadAdmin1Layer() {
  try {
    const r = await fetch('data/ne_10m_admin1_slim.geojson');
    if (!r.ok) return;
    const geo = await r.json();

    map.addSource('admin1', { type: 'geojson', data: geo });

    map.addLayer({
      id: 'admin1-fill',
      type: 'fill',
      source: 'admin1',
      minzoom: 3,
      paint: {
        'fill-color': buildAdmin1ColorExpr(),
        'fill-opacity': 0.7,
      },
    }, 'countries-fill');

    map.addLayer({
      id: 'admin1-border',
      type: 'line',
      source: 'admin1',
      minzoom: 3,
      paint: {
        'line-color': '#ffffff',
        'line-width': 0.3,
        'line-opacity': 0.4,
      },
    }, 'countries-border');

    console.info('Admin-1 (estados) carregado.');
  } catch (_) {
    // Silencioso — admin1 é opcional no MVP
  }
}

// ── Expressões de cor MapLibre ────────────────────────────────────────────────

/**
 * Constrói expressão `match` para colorir países (admin-0) de acordo com os filtros.
 * Propriedade usada: ADM0_A3 (ISO-A3 do Natural Earth).
 */
function buildCountryColorExpr() {
  const expr = ['match', ['get', 'ADM0_A3']];
  const added = new Set();

  // Indexar banco por iso_3
  const byIso = indexByIso();

  for (const [iso, entries] of Object.entries(byIso)) {
    const color = topColor(entries);
    if (color && color !== 'cinza' && !added.has(iso)) {
      expr.push(iso, COLORS[color]);
      added.add(iso);
    }
  }
  // match precisa de pelo menos um par input→output antes do default
  if (expr.length < 4) return COLORS.cinza;
  expr.push(COLORS.cinza); // default
  return expr;
}

/**
 * Expressão de cor para admin-1 (estados/províncias).
 * Filtra apenas entradas de nível estadual e municipal.
 * Propriedade: adm0_a3 (país) + name (nome do estado para match fuzzy).
 */
function buildAdmin1ColorExpr() {
  // Simplificação MVP: colorir estados pelo país (herdar cor do país pai)
  // Substituir por match nome-estado quando o banco tiver join com admin1 IDs
  return buildCountryColorExpr();
}

/** Agrupa banco filtrado por iso_3 */
function indexByIso() {
  const idx = {};
  for (const entry of getFilteredEntries()) {
    const iso = entry.iso_3;
    if (!iso) continue;
    if (!idx[iso]) idx[iso] = [];
    idx[iso].push(entry);
  }
  return idx;
}

/** Retorna todas as entradas do banco que passam pelos filtros ativos */
function getFilteredEntries() {
  return banco.filter(e => {
    // Filtro de camada (fonte + status)
    let inLayer = false;
    for (const [layerKey, def] of Object.entries(LAYER_MAP)) {
      if (filters.layers.has(layerKey) &&
          def.fontes.includes(e.fonte) &&
          def.status.some(s => e.status?.includes(s))) {
        inLayer = true;
        break;
      }
    }
    if (!inLayer) return false;

    // Filtro de nível
    if (!filters.niveis.has(e.nivel)) return false;

    // Filtro de ano
    if (e.ano && (e.ano < filters.ano_min || e.ano > filters.ano_max)) return false;

    return true;
  });
}

/** Retorna a cor de maior prioridade entre as entradas de um país */
function topColor(entries) {
  const colors = new Set(entries.map(e => e.cor_mapa));
  return COLOR_PRIORITY.find(c => colors.has(c)) ?? 'cinza';
}

// ── Eventos do mapa ───────────────────────────────────────────────────────────

let hoveredIso = null;

function onCountryHover(e) {
  if (!e.features.length) return;
  const iso = e.features[0].properties.ADM0_A3;
  if (iso === hoveredIso) return;
  hoveredIso = iso;
  map.getCanvas().style.cursor = 'pointer';
}

function onCountryLeave() {
  hoveredIso = null;
  map.getCanvas().style.cursor = '';
}

function onCountryClick(e) {
  if (!e.features.length) return;
  const feat = e.features[0];
  const iso = feat.properties.ADM0_A3;
  const name = feat.properties.NAME_PT
    || feat.properties.NAME_LONG
    || feat.properties.NAME
    || iso;

  selectCountry(iso, name);
}

function selectCountry(iso, name) {
  // Deselecionar anterior
  if (selectedIso && selectedIso !== iso) {
    map.setFeatureState({ source: 'countries', id: selectedIso }, { selected: false });
  }
  selectedIso = iso;
  map.setFeatureState({ source: 'countries', id: iso }, { selected: true });

  showInfoPanel(iso, name);
}

// ── Painel de informação ──────────────────────────────────────────────────────

function showInfoPanel(iso, name) {
  document.getElementById('info-title').textContent = name;
  document.getElementById('info-panel').classList.remove('hidden');
  renderInfoTab(iso, activeTab);
}

function hideInfoPanel() {
  document.getElementById('info-panel').classList.add('hidden');
  if (selectedIso) {
    map.setFeatureState({ source: 'countries', id: selectedIso }, { selected: false });
  }
  selectedIso = null;
}

function renderInfoTab(iso, tab) {
  const list = document.getElementById('info-list');
  list.innerHTML = '';

  const allEntries = banco.filter(e => e.iso_3 === iso);

  let entries;
  if (tab === 'declaracoes') {
    entries = allEntries.filter(e => ['CEDAMIA', 'MANUAL'].includes(e.fonte));
  } else if (tab === 'atribuicao') {
    entries = allEntries.filter(e => e.fonte === 'WWA');
  } else {
    entries = allEntries.filter(e => e.fonte === 'ALMOST-CED');
  }

  if (!entries.length) {
    list.innerHTML = `<li class="no-data">Sem dados nesta categoria para ${iso}.</li>`;
    return;
  }

  for (const e of entries) {
    const li = document.createElement('li');
    li.innerHTML = `
      <div class="entry-entity">
        <span class="entry-badge badge-${e.cor_mapa}">${nivelLabel(e.nivel)}</span>
        ${escHtml(e.entidade)}
      </div>
      <div class="entry-meta">
        ${e.data_completa ? `📅 ${escHtml(e.data_completa)}` : ''}
        ${e.regiao ? ` · 📍 ${escHtml(e.regiao)}` : ''}
        ${e.url_documento
          ? ` · <a href="${escHtml(e.url_documento)}" target="_blank" rel="noopener">Documento ↗</a>`
          : ''}
        ${e.fator_risco_wwa ? `<br>⚠️ ${escHtml(e.fator_risco_wwa)}` : ''}
        ${e.justificativa ? `<br>ℹ️ ${escHtml(e.justificativa)}` : ''}
        ${!e.verificado ? ' <span title="Não verificado manualmente">⚠️</span>' : ''}
      </div>
    `;
    list.appendChild(li);
  }
}

function nivelLabel(nivel) {
  return { nacional: 'Nacional', estadual: 'Estadual', municipal: 'Municipal' }[nivel] ?? nivel;
}

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Filtros ───────────────────────────────────────────────────────────────────

function setupFiltersUI() {
  // Checkboxes de camada
  document.querySelectorAll('input[name="fonte"]').forEach(cb => {
    cb.addEventListener('change', () => {
      if (cb.checked) {
        filters.layers.add(cb.value);
      } else {
        filters.layers.delete(cb.value);
      }
      applyFilters();
    });
  });

  // Pills de nível
  document.querySelectorAll('#filter-nivel .pill').forEach(btn => {
    btn.addEventListener('click', () => {
      const val = btn.dataset.value;
      btn.classList.toggle('active');
      if (btn.classList.contains('active')) {
        filters.niveis.add(val);
      } else {
        filters.niveis.delete(val);
      }
      applyFilters();
    });
  });

  // Sliders de ano
  const sliderMin = document.getElementById('ano-min');
  const sliderMax = document.getElementById('ano-max');
  const labelMin  = document.getElementById('ano-min-label');
  const labelMax  = document.getElementById('ano-max-label');

  function syncSliders() {
    let vMin = parseInt(sliderMin.value, 10);
    let vMax = parseInt(sliderMax.value, 10);
    if (vMin > vMax) [vMin, vMax] = [vMax, vMin];
    filters.ano_min = vMin;
    filters.ano_max = vMax;
    labelMin.textContent = vMin;
    labelMax.textContent = vMax;
    applyFilters();
  }
  sliderMin.addEventListener('input', syncSliders);
  sliderMax.addEventListener('input', syncSliders);

  // Busca por país
  const searchInput = document.getElementById('pais-search');
  const resultsList = document.getElementById('search-results');

  searchInput.addEventListener('input', () => {
    const q = searchInput.value.trim().toLowerCase();
    resultsList.innerHTML = '';
    if (!q) return;

    // Coletar países únicos que batem com a busca
    const seen = new Set();
    const matches = [];
    for (const e of banco) {
      const iso = e.iso_3;
      if (seen.has(iso)) continue;
      if (!iso) continue;
      const pais = (e.pais || '').toLowerCase();
      const entidade = (e.entidade || '').toLowerCase();
      if (pais.includes(q) || entidade.includes(q) || iso.toLowerCase().includes(q)) {
        seen.add(iso);
        matches.push({ iso, pais: e.pais });
      }
      if (matches.length >= 8) break;
    }

    for (const { iso, pais } of matches) {
      const li = document.createElement('li');
      li.innerHTML = `<span>${escHtml(pais)}</span><span class="iso-badge">${iso}</span>`;
      li.addEventListener('click', () => {
        searchInput.value = '';
        resultsList.innerHTML = '';
        flyToCountry(iso, pais);
      });
      resultsList.appendChild(li);
    }
  });

  // Botão fechar info-panel
  document.getElementById('info-close').addEventListener('click', hideInfoPanel);

  // Tabs do info-panel
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeTab = btn.dataset.tab;
      if (selectedIso) {
        renderInfoTab(selectedIso, activeTab);
      }
    });
  });

  // Toggle sidebar
  document.getElementById('sidebar-toggle').addEventListener('click', () => {
    document.getElementById('sidebar').classList.add('collapsed');
    document.getElementById('sidebar-open').hidden = false;
  });
  document.getElementById('sidebar-open').addEventListener('click', () => {
    document.getElementById('sidebar').classList.remove('collapsed');
    document.getElementById('sidebar-open').hidden = true;
  });
}

function flyToCountry(iso, name) {
  if (!map) return;
  // Tentar encontrar o centróide do país no GeoJSON
  const source = map.getSource('countries');
  if (source) {
    const features = map.querySourceFeatures('countries', {
      filter: ['==', ['get', 'ADM0_A3'], iso],
    });
    if (features.length) {
      const bounds = new maplibregl.LngLatBounds();
      features[0].geometry.coordinates.flat(Infinity).forEach((c, i, a) => {
        if (i % 2 === 0) bounds.extend([c, a[i + 1]]);
      });
      if (!bounds.isEmpty()) {
        map.fitBounds(bounds, { padding: 80, maxZoom: 6, duration: 800 });
      }
    }
  }
  selectCountry(iso, name);
}

// ── Atualização de estado ─────────────────────────────────────────────────────

function applyFilters() {
  if (!map || !map.isStyleLoaded()) return;

  const expr = buildCountryColorExpr();

  if (map.getLayer('countries-fill')) {
    map.setPaintProperty('countries-fill', 'fill-color', expr);
  }
  // admin1-fill desabilitado no MVP
  // if (map.getLayer('admin1-fill')) {
  //   map.setPaintProperty('admin1-fill', 'fill-color', buildAdmin1ColorExpr());
  // }

  updateStats();
  updateLayerCounts();

  // Atualizar info panel se aberto
  if (selectedIso) {
    renderInfoTab(selectedIso, activeTab);
  }
}

function updateStats() {
  const filtered = getFilteredEntries();
  const isos = new Set(filtered.map(e => e.iso_3).filter(Boolean));
  document.getElementById('stat-jurisdictions').textContent = filtered.length.toLocaleString('pt-BR');
  document.getElementById('stat-countries').textContent = isos.size;
}

function updateLayerCounts() {
  const filtered = getFilteredEntries();

  const countCed    = filtered.filter(e => ['CEDAMIA', 'MANUAL'].includes(e.fonte)).length;
  const countWwa    = filtered.filter(e => e.fonte === 'WWA').length;
  const countAlmost = filtered.filter(e => e.fonte === 'ALMOST-CED').length;

  document.getElementById('count-ced-formal').textContent = countCed ? `${countCed} decl.` : '';
  document.getElementById('count-wwa').textContent        = countWwa  ? `${countWwa} países` : '';
  document.getElementById('count-almost').textContent     = countAlmost ? `${countAlmost} casos` : '';
}

function hideLoading() {
  const el = document.getElementById('loading');
  el.classList.add('done');
  setTimeout(() => el.remove(), 500);
}

// ── Entry point ───────────────────────────────────────────────────────────────
init();
