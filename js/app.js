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
let selectedScope = null; // { iso, ne_id?, admin2_name?, displayName }

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
    const hashState = readStateFromHash();
    if (hashState) applyHashStateToFilters(hashState);
    setupMap(hashState);
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

function setupMap(hashState) {
  const view = hashState?.view;
  map = new maplibregl.Map({
    container: 'map',
    style: 'https://tiles.openfreemap.org/styles/liberty',
    center: view ? [view.lng, view.lat] : [10, 20],
    zoom: view ? view.z : 2,
    minZoom: 1.5,
    maxZoom: 14,
    attributionControl: false,
  });

  map.addControl(new maplibregl.NavigationControl(), 'top-right');
  map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');

  map.on('load', () => onMapLoad(hashState));
  map.on('error', e => console.warn('MapLibre:', e.error?.message));
}

async function onMapLoad(hashState) {  // async: aguarda loadAdmin1Layer()
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

  // Layer: fill de países — opacidade reduz ao zoom in (admin-1 assume)
  map.addLayer({
    id: 'countries-fill',
    type: 'fill',
    source: 'countries',
    paint: {
      'fill-color': buildCountryColorExpr(),
      'fill-opacity': [
        'interpolate', ['linear'], ['zoom'],
        2, 0.75,
        4, 0.45,
        6, 0.20,
      ],
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

  // Admin-1 (estados/províncias) — Phase 2 com Natural Earth 50m + join ne_id
  await loadAdmin1Layer();

  // Pontos geocodificados (cidades/municípios) — Phase 3 com clustering
  loadPointsLayer();

  // Admin-2 (top-5 países) lazy: carrega só quando o usuário aproxima
  map.on('zoom', maybeLoadAdmin2);

  // Hover de país (mantém handler por layer — cursor + tracking)
  map.on('mousemove', 'countries-fill', onCountryHover);
  map.on('mouseleave', 'countries-fill', onCountryLeave);

  // Clique unificado: queryRenderedFeatures com lista priorizada evita o problema
  // de event bubbling do MapLibre (clique em admin2 também dispararia admin1 e
  // countries, e o último handler venceria).
  map.on('click', onMapClick);

  hideLoading();
  setupFiltersUI();
  syncUIFromFilters();
  updateStats();
  updateLayerCounts();

  if (hashState?.scope) {
    restoreScopeFromHash(hashState.scope);
  }

  map.on('moveend', writeStateToHash);
  window.addEventListener('hashchange', onHashChange);
}

/** Retorna o id da primeira camada de símbolos (para inserir layers abaixo de labels) */
function firstSymbolLayer() {
  const layers = map.getStyle()?.layers ?? [];
  return layers.find(l => l.type === 'symbol')?.id;
}

/** Carrega admin-1 (estados/províncias) — Natural Earth 50m com promoteId ne_id */
async function loadAdmin1Layer() {
  try {
    const r = await fetch('data/ne_50m_admin1_slim.geojson');
    if (!r.ok) {
      console.info('Admin-1 GeoJSON não disponível (execute setup.py). Pulando.');
      return;
    }
    const geo = await r.json();

    // promoteId: 'ne_id' → cada feature recebe o ne_id como ID numérico do MapLibre
    // Isso permite ['id'] nas expressões de paint para lookup O(1)
    map.addSource('admin1', {
      type: 'geojson',
      data: geo,
      promoteId: 'ne_id',
    });

    // Inserir admin1-fill ACIMA de countries-border mas ABAIXO de countries-highlight
    map.addLayer({
      id: 'admin1-fill',
      type: 'fill',
      source: 'admin1',
      minzoom: 3,
      paint: {
        'fill-color': buildAdmin1ColorExpr(),
        // Aparece suavemente ao dar zoom in
        'fill-opacity': [
          'interpolate', ['linear'], ['zoom'],
          3, 0,
          4, 0.82,
        ],
      },
    }, 'countries-highlight'); // inserido abaixo do highlight de seleção

    map.addLayer({
      id: 'admin1-border',
      type: 'line',
      source: 'admin1',
      minzoom: 3,
      paint: {
        'line-color': '#ffffff',
        'line-width': 0.5,
        'line-opacity': [
          'interpolate', ['linear'], ['zoom'],
          3, 0,
          4, 0.5,
        ],
      },
    }, 'countries-highlight');

    // Hover de admin-1 (clique é tratado no handler global onMapClick)
    map.on('mousemove', 'admin1-fill', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'admin1-fill', () => { map.getCanvas().style.cursor = ''; });

    console.info(`Admin-1 carregado: ${geo.features?.length ?? '?'} polígonos.`);
  } catch (err) {
    console.warn('Admin-1 não carregado:', err.message);
  }
}

/**
 * Phase 3 — Admin-2 (município/condado) para top-5 países, lazy-loaded.
 * O arquivo data/admin2_top5.geojson é gerado por build/build_admin2_polygons.py.
 * Só baixa quando o usuário ultrapassa zoom 6 (evita pagar custo no carregamento inicial).
 */
let admin2State = 'idle'; // idle | loading | loaded | missing

async function maybeLoadAdmin2() {
  if (admin2State !== 'idle') return;
  if (map.getZoom() < 6) return;
  admin2State = 'loading';
  await loadAdmin2Layer();
}

async function loadAdmin2Layer() {
  try {
    const r = await fetch('data/admin2_top5.geojson');
    if (!r.ok) {
      console.info('Admin-2 GeoJSON não disponível (execute build/build_admin2_polygons.py).');
      admin2State = 'missing';
      return;
    }
    const geo = await r.json();

    map.addSource('admin2', { type: 'geojson', data: geo });

    map.addLayer({
      id: 'admin2-fill',
      type: 'fill',
      source: 'admin2',
      minzoom: 5,
      paint: {
        'fill-color': buildAdmin2ColorExpr(),
        'fill-opacity': [
          'interpolate', ['linear'], ['zoom'],
          5, 0,
          7, 0.7,
        ],
      },
    }, 'countries-highlight');

    map.addLayer({
      id: 'admin2-border',
      type: 'line',
      source: 'admin2',
      minzoom: 6,
      paint: {
        'line-color': '#ffffff',
        'line-width': 0.4,
        'line-opacity': [
          'interpolate', ['linear'], ['zoom'],
          6, 0,
          7, 0.5,
        ],
      },
    }, 'countries-highlight');

    // Clique de admin-2 é tratado pelo handler global onMapClick.
    admin2State = 'loaded';
    console.info(`Admin-2 carregado: ${geo.features?.length ?? '?'} polígonos (top-5).`);
  } catch (err) {
    console.warn('Admin-2 não carregado:', err.message);
    admin2State = 'missing';
  }
}

/**
 * Cores admin-2: casa o município pelo nome (props.NAME_2) com entidade do banco
 * dentro do mesmo país (props.ISO_3). Match exato case-insensitive.
 * Polígonos sem match ficam transparentes (mostra terreno por baixo).
 */
function buildAdmin2ColorExpr() {
  // Indexar entradas filtradas por iso → nome normalizado → cor
  const idx = {};
  for (const e of getFilteredEntries()) {
    if (e.nivel === 'nacional') continue;
    const iso = e.iso_3;
    if (!iso) continue;
    const name = normName(e.entidade);
    if (!name) continue;
    if (!idx[iso]) idx[iso] = {};
    const prev = idx[iso][name];
    // Manter cor de maior prioridade entre múltiplas entradas
    if (!prev || COLOR_PRIORITY.indexOf(e.cor_mapa) < COLOR_PRIORITY.indexOf(prev)) {
      idx[iso][name] = e.cor_mapa;
    }
  }

  // MapLibre case: usa concat(iso, '|', name) como chave
  const expr = ['match',
    ['concat', ['get', 'ISO_3'], '|',
      ['downcase', ['coalesce', ['get', 'NAME_2'], '']]],
  ];

  let pairs = 0;
  for (const [iso, byName] of Object.entries(idx)) {
    for (const [name, color] of Object.entries(byName)) {
      if (color && color !== 'cinza') {
        expr.push(`${iso}|${name}`, COLORS[color]);
        pairs++;
      }
    }
  }
  if (pairs === 0) return 'rgba(0,0,0,0)';
  expr.push('rgba(0,0,0,0)');
  return expr;
}

/** Normaliza nome de município para casar com NAME_2 do GADM (lowercase + trim). */
function normName(s) {
  if (!s) return '';
  let n = String(s).toLowerCase().trim();
  // Remover prefixos/sufixos comuns que não aparecem no GADM
  n = n.replace(/^(city of|town of|district of|municipality of|borough of)\s+/i, '');
  n = n.replace(/\s+(city council|town council|borough council|district council|county council|municipal council|council)\s*$/i, '');
  return n.trim();
}

/**
 * Phase 3 — Camada de pontos com clustering nativo MapLibre.
 * Mostra um círculo por jurisdição geocodificada. Em zoom baixo agrupa
 * em clusters. Em zoom alto mostra pontos individuais coloridos por cor_mapa.
 */
function loadPointsLayer() {
  const fc = buildPointsGeoJSON();

  map.addSource('points', {
    type: 'geojson',
    data: fc,
    cluster: true,
    clusterMaxZoom: 7,    // ao ultrapassar este zoom, separa em pontos individuais
    clusterRadius: 45,    // raio de agregação em pixels
  });

  // Clusters: círculo dimensionado e colorido pelo número de pontos
  map.addLayer({
    id: 'clusters',
    type: 'circle',
    source: 'points',
    filter: ['has', 'point_count'],
    paint: {
      'circle-color': [
        'step', ['get', 'point_count'],
        '#F4D03F',  10,   // < 10 → amarelo
        '#E67E22',  50,   // < 50 → laranja
        '#C0392B',        // ≥ 50 → vermelho
      ],
      'circle-radius': [
        'step', ['get', 'point_count'],
        14, 10, 18, 50, 24,
      ],
      'circle-stroke-width': 2,
      'circle-stroke-color': '#ffffff',
      'circle-opacity': 0.9,
    },
  });

  // Contador no centro do cluster
  map.addLayer({
    id: 'cluster-count',
    type: 'symbol',
    source: 'points',
    filter: ['has', 'point_count'],
    layout: {
      'text-field': '{point_count_abbreviated}',
      'text-font': ['Noto Sans Regular'],
      'text-size': 12,
    },
    paint: {
      'text-color': '#ffffff',
    },
  });

  // Pontos individuais (não-cluster)
  map.addLayer({
    id: 'unclustered-point',
    type: 'circle',
    source: 'points',
    filter: ['!', ['has', 'point_count']],
    paint: {
      'circle-color': [
        'match', ['get', 'cor'],
        'vermelho', COLORS.vermelho,
        'laranja',  COLORS.laranja,
        'amarelo',  COLORS.amarelo,
        'azul',     COLORS.azul,
        'roxo',     COLORS.roxo,
        COLORS.cinza,
      ],
      'circle-radius': [
        'interpolate', ['linear'], ['zoom'],
        5, 4,
        10, 7,
      ],
      'circle-stroke-width': 1.5,
      'circle-stroke-color': '#ffffff',
      'circle-opacity': 0.92,
    },
  });

  // Clique em cluster → zoom in
  map.on('click', 'clusters', e => {
    const feat = e.features[0];
    const clusterId = feat.properties.cluster_id;
    map.getSource('points').getClusterExpansionZoom(clusterId).then(zoom => {
      map.easeTo({ center: feat.geometry.coordinates, zoom });
    });
  });

  // Clique em ponto individual é tratado pelo handler global onMapClick.

  // Cursor pointer ao passar por cluster/ponto
  for (const id of ['clusters', 'unclustered-point']) {
    map.on('mouseenter', id, () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', id, () => { map.getCanvas().style.cursor = ''; });
  }

  // Tooltip ao passar sobre ponto individual
  const popup = new maplibregl.Popup({
    closeButton: false, closeOnClick: false, offset: 10,
  });
  map.on('mouseenter', 'unclustered-point', e => {
    const p = e.features[0].properties;
    popup
      .setLngLat(e.features[0].geometry.coordinates)
      .setHTML(`<strong>${escHtml(p.entidade)}</strong>${p.regiao ? `<br><small>${escHtml(p.regiao)}</small>` : ''}${p.ano ? `<br><small>${p.ano}</small>` : ''}`)
      .addTo(map);
  });
  map.on('mouseleave', 'unclustered-point', () => popup.remove());

  console.info(`Points carregados: ${fc.features.length} jurisdições geocodificadas.`);
}

/** Constrói FeatureCollection com um Point por entrada do banco que tem lat/lon. */
function buildPointsGeoJSON() {
  const features = [];
  for (const e of getFilteredEntries()) {
    if (typeof e.lat !== 'number' || typeof e.lon !== 'number') continue;
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [e.lon, e.lat] },
      properties: {
        iso:        e.iso_3,
        entidade:   e.entidade,
        regiao:     e.regiao || '',
        ano:        e.ano || '',
        cor:        e.cor_mapa,
        fonte:      e.fonte,
        adm1_ne_id: e.adm1_ne_id ?? null,
      },
    });
  }
  return { type: 'FeatureCollection', features };
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
 * Usa ['id'] para acessar o ne_id (promoteId na source),
 * casando com adm1_ne_id do banco. Prioridade: laranja > amarelo > outros.
 */
function buildAdmin1ColorExpr() {
  const expr = ['match', ['id']];

  const filtered = getFilteredEntries();

  // Agrupar entradas sub-nacionais por adm1_ne_id
  const byNeId = {};
  for (const e of filtered) {
    if (!e.adm1_ne_id) continue;  // nulos e nacionais ficam de fora
    const id = e.adm1_ne_id;      // já é número (parse_int no setup.py)
    if (!byNeId[id]) byNeId[id] = [];
    byNeId[id].push(e);
  }

  for (const [idStr, entries] of Object.entries(byNeId)) {
    const neId = Number(idStr);
    const color = topColor(entries);
    if (color && color !== 'cinza') {
      expr.push(neId, COLORS[color]);
    }
  }

  // match exige ao menos um par input→output antes do default
  if (expr.length < 4) return 'rgba(0,0,0,0)';  // totalmente transparente se vazio
  expr.push('rgba(0,0,0,0)');  // default transparente (mostra apenas estados com dados)
  return expr;
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

/**
 * Handler unificado de clique. Usa queryRenderedFeatures com lista priorizada
 * para escolher o escopo mais granular (ponto > admin2 > admin1 > país),
 * evitando que cliques em polígonos empilhados disparem múltiplos handlers.
 */
function onMapClick(e) {
  const layers = ['unclustered-point', 'admin2-fill', 'admin1-fill', 'countries-fill']
    .filter(id => map.getLayer(id));
  const hits = map.queryRenderedFeatures(e.point, { layers });
  if (!hits.length) return;
  const feat = hits[0];
  switch (feat.layer.id) {
    case 'unclustered-point': return onPointClick(feat);
    case 'admin2-fill':       return onAdmin2Click(feat);
    case 'admin1-fill':       return onAdmin1Click(feat);
    case 'countries-fill':    return onCountryClick(feat);
  }
}

function onCountryClick(feat) {
  const iso = feat.properties.ADM0_A3;
  if (!iso) return;
  const name = feat.properties.NAME_PT
    || feat.properties.NAME_LONG
    || feat.properties.NAME
    || iso;
  selectScope({ iso }, name);
}

/** Clique em polígono admin-1 — escopo = país + ne_id do estado */
function onAdmin1Click(feat) {
  const props = feat.properties;
  const iso = (props.adm0_a3 || '').toUpperCase();
  if (!iso) return;
  const ne_id = feat.id; // MapLibre populou via promoteId: 'ne_id'
  const entry = banco.find(b => b.iso_3 === iso);
  const paisName  = entry?.pais || iso;
  const stateName = props.name_en || props.name || '';
  const displayName = stateName ? `${paisName} › ${stateName}` : paisName;
  selectScope({ iso, ne_id }, displayName);
}

/** Clique em polígono admin-2 — escopo = país + nome do município */
function onAdmin2Click(feat) {
  const props = feat.properties;
  const iso = (props.ISO_3 || '').toUpperCase();
  if (!iso) return;
  const admin2_name = props.NAME_2 || '';
  if (!admin2_name) return;
  const entry = banco.find(b => b.iso_3 === iso);
  const paisName = entry?.pais || iso;
  const displayName = `${paisName} › ${admin2_name}`;
  selectScope({ iso, admin2_name }, displayName);
}

/** Clique em ponto individual — drill até o estado se conhecido. */
function onPointClick(feat) {
  const props = feat.properties;
  const iso = (props.iso || '').toUpperCase();
  if (!iso) return;
  const entry = banco.find(b => b.iso_3 === iso);
  const paisName = entry?.pais || iso;
  // adm1_ne_id pode vir como número ou string (depende do MapLibre serialization)
  const ne_id_raw = props.adm1_ne_id;
  const ne_id = (ne_id_raw === null || ne_id_raw === '' || ne_id_raw === undefined)
    ? null : Number(ne_id_raw);
  if (ne_id && !Number.isNaN(ne_id)) {
    const region = props.regiao || '';
    const displayName = region ? `${paisName} › ${region}` : paisName;
    selectScope({ iso, ne_id }, displayName);
  } else {
    selectScope({ iso }, paisName);
  }
}

/** Aplica o escopo: atualiza highlights e abre painel. */
function selectScope(scope, displayName) {
  clearHighlights();
  selectedScope = { ...scope, displayName };
  if (scope.iso && map.getSource('countries')) {
    map.setFeatureState({ source: 'countries', id: scope.iso }, { selected: true });
  }
  if (scope.ne_id != null && map.getSource('admin1')) {
    map.setFeatureState({ source: 'admin1', id: scope.ne_id }, { selected: true });
  }
  showInfoPanel(displayName);
  writeStateToHash();
}

/** Limpa highlights do escopo atual. Idempotente. */
function clearHighlights() {
  if (!selectedScope) return;
  if (selectedScope.iso && map.getSource('countries')) {
    map.setFeatureState({ source: 'countries', id: selectedScope.iso }, { selected: false });
  }
  if (selectedScope.ne_id != null && map.getSource('admin1')) {
    map.setFeatureState({ source: 'admin1', id: selectedScope.ne_id }, { selected: false });
  }
}

// ── Painel de informação ──────────────────────────────────────────────────────

function showInfoPanel(displayName) {
  document.getElementById('info-title').textContent = displayName;
  document.getElementById('info-panel').classList.remove('hidden');
  renderAllSections();
}

function hideInfoPanel() {
  document.getElementById('info-panel').classList.add('hidden');
  clearHighlights();
  selectedScope = null;
  writeStateToHash();
}

/** Filtra entradas do banco pelo escopo selecionado (cascata iso → ne_id → admin2). */
function filteredForScope(scope) {
  let xs = banco.filter(e => e.iso_3 === scope.iso);
  if (scope.ne_id != null) {
    xs = xs.filter(e => e.adm1_ne_id === scope.ne_id);
  }
  if (scope.admin2_name) {
    const target = normName(scope.admin2_name);
    xs = xs.filter(e => normName(e.entidade) === target);
  }
  return xs;
}

/** Renderiza as 3 seções (Declarações / WWA / Quase-CED) ao mesmo tempo. */
function renderAllSections() {
  if (!selectedScope) return;
  const allEntries = filteredForScope(selectedScope);
  const buckets = {
    declaracoes: allEntries.filter(e => ['CEDAMIA','MANUAL'].includes(e.fonte)),
    atribuicao:  allEntries.filter(e => e.fonte === 'WWA'),
    quase:       allEntries.filter(e => e.fonte === 'ALMOST-CED'),
  };
  const label = escHtml(selectedScope.displayName || selectedScope.iso || '');

  for (const [key, entries] of Object.entries(buckets)) {
    const list  = document.querySelector(`[data-list-for="${key}"]`);
    const count = document.querySelector(`[data-count-for="${key}"]`);
    if (!list || !count) continue;

    count.textContent = entries.length;
    if (entries.length === 0) count.setAttribute('data-zero', '');
    else                       count.removeAttribute('data-zero');

    list.innerHTML = '';
    if (!entries.length) {
      list.innerHTML = `<li class="no-data">Sem dados nesta categoria para ${label}.</li>`;
      continue;
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
  selectScope({ iso }, name);
}

// ── Atualização de estado ─────────────────────────────────────────────────────

function applyFilters() {
  if (!map || !map.isStyleLoaded()) return;

  if (map.getLayer('countries-fill')) {
    map.setPaintProperty('countries-fill', 'fill-color', buildCountryColorExpr());
  }

  if (map.getLayer('admin1-fill')) {
    map.setPaintProperty('admin1-fill', 'fill-color', buildAdmin1ColorExpr());
  }

  if (map.getSource('points')) {
    map.getSource('points').setData(buildPointsGeoJSON());
  }

  if (map.getLayer('admin2-fill')) {
    map.setPaintProperty('admin2-fill', 'fill-color', buildAdmin2ColorExpr());
  }

  updateStats();
  updateLayerCounts();

  // Atualizar info panel se aberto
  if (selectedScope) {
    renderAllSections();
  }

  writeStateToHash();
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

// ── Deep linking (estado dos filtros + escopo + view na URL) ──────────────────

const DEFAULTS = {
  layers: ['ced-formal', 'wwa', 'almost-ced'],
  niveis: ['nacional', 'estadual', 'municipal'],
  ano_min: 1990,
  ano_max: 2026,
  center: [10, 20],
  zoom: 2,
};

/** Lê e desserializa o hash atual. Retorna null se vazio. */
function readStateFromHash() {
  const raw = location.hash.replace(/^#/, '');
  if (!raw) return null;
  const p = new URLSearchParams(raw);
  const state = {};

  if (p.has('layers')) state.layers = p.get('layers').split(',').filter(Boolean);
  if (p.has('niveis')) state.niveis = p.get('niveis').split(',').filter(Boolean);

  const ano = p.get('ano');
  if (ano) {
    const m = ano.match(/^(\d{4})-(\d{4})$/);
    if (m) {
      state.ano_min = parseInt(m[1], 10);
      state.ano_max = parseInt(m[2], 10);
    }
  }

  const iso = p.get('iso');
  if (iso) {
    state.scope = { iso: iso.toUpperCase() };
    const ne = p.get('ne');
    if (ne && !Number.isNaN(Number(ne))) state.scope.ne_id = Number(ne);
    const m2 = p.get('m2');
    if (m2) state.scope.admin2_name = m2;
  }

  const v = p.get('v');
  if (v) {
    const [lng, lat, z] = v.split(',').map(Number);
    if ([lng, lat, z].every(Number.isFinite)) state.view = { lng, lat, z };
  }

  return state;
}

/** Aplica filtros desserializados ao estado global (sem tocar na UI). */
function applyHashStateToFilters(state) {
  if (state.layers) filters.layers = new Set(state.layers);
  if (state.niveis) filters.niveis = new Set(state.niveis);
  if (Number.isFinite(state.ano_min)) filters.ano_min = state.ano_min;
  if (Number.isFinite(state.ano_max)) filters.ano_max = state.ano_max;
}

/** Reflete `filters` nos controles da UI (checkboxes, pills, sliders). */
function syncUIFromFilters() {
  document.querySelectorAll('input[name="fonte"]').forEach(cb => {
    cb.checked = filters.layers.has(cb.value);
  });
  document.querySelectorAll('#filter-nivel .pill').forEach(btn => {
    btn.classList.toggle('active', filters.niveis.has(btn.dataset.value));
  });
  const sliderMin = document.getElementById('ano-min');
  const sliderMax = document.getElementById('ano-max');
  const labelMin  = document.getElementById('ano-min-label');
  const labelMax  = document.getElementById('ano-max-label');
  if (sliderMin) sliderMin.value = filters.ano_min;
  if (sliderMax) sliderMax.value = filters.ano_max;
  if (labelMin)  labelMin.textContent  = filters.ano_min;
  if (labelMax)  labelMax.textContent  = filters.ano_max;
}

/** Restaura escopo a partir do hash. Resolve nomes via banco. */
function restoreScopeFromHash(scope) {
  const entry = banco.find(b => b.iso_3 === scope.iso);
  const paisName = entry?.pais || scope.iso;

  if (scope.admin2_name) {
    selectScope(
      { iso: scope.iso, admin2_name: scope.admin2_name },
      `${paisName} › ${scope.admin2_name}`,
    );
  } else if (scope.ne_id != null) {
    const sub = banco.find(b => b.iso_3 === scope.iso && b.adm1_ne_id === scope.ne_id);
    const display = sub?.regiao ? `${paisName} › ${sub.regiao}` : paisName;
    selectScope({ iso: scope.iso, ne_id: scope.ne_id }, display);
  } else {
    selectScope({ iso: scope.iso }, paisName);
  }
}

/** Serializa o estado atual e grava em location.hash (sem entrada de histórico). */
function writeStateToHash() {
  if (!map) return;
  const p = new URLSearchParams();

  const layers = [...filters.layers].sort();
  if (layers.length !== DEFAULTS.layers.length ||
      !DEFAULTS.layers.every(l => filters.layers.has(l))) {
    p.set('layers', layers.join(','));
  }

  const niveis = [...filters.niveis].sort();
  if (niveis.length !== DEFAULTS.niveis.length ||
      !DEFAULTS.niveis.every(n => filters.niveis.has(n))) {
    p.set('niveis', niveis.join(','));
  }

  if (filters.ano_min !== DEFAULTS.ano_min || filters.ano_max !== DEFAULTS.ano_max) {
    p.set('ano', `${filters.ano_min}-${filters.ano_max}`);
  }

  if (selectedScope?.iso) {
    p.set('iso', selectedScope.iso);
    if (selectedScope.ne_id != null) p.set('ne', String(selectedScope.ne_id));
    if (selectedScope.admin2_name)   p.set('m2', selectedScope.admin2_name);
  }

  const c = map.getCenter();
  const z = map.getZoom();
  const movedView = Math.abs(z - DEFAULTS.zoom) > 0.1
                 || Math.abs(c.lng - DEFAULTS.center[0]) > 0.5
                 || Math.abs(c.lat - DEFAULTS.center[1]) > 0.5;
  if (movedView) {
    p.set('v', `${c.lng.toFixed(3)},${c.lat.toFixed(3)},${z.toFixed(2)}`);
  }

  const next = p.toString() ? `#${p}` : location.pathname + location.search;
  if (location.hash !== (p.toString() ? `#${p}` : '')) {
    history.replaceState(null, '', next);
  }
}

/** Reage a hashchange externo (paste de URL, back/forward com pushState futuro). */
function onHashChange() {
  const state = readStateFromHash() ?? {};
  // Restaurar filtros (volta ao default se hash limpo)
  filters.layers = new Set(state.layers ?? DEFAULTS.layers);
  filters.niveis = new Set(state.niveis ?? DEFAULTS.niveis);
  filters.ano_min = Number.isFinite(state.ano_min) ? state.ano_min : DEFAULTS.ano_min;
  filters.ano_max = Number.isFinite(state.ano_max) ? state.ano_max : DEFAULTS.ano_max;
  syncUIFromFilters();
  applyFilters();

  if (state.view) {
    map.easeTo({ center: [state.view.lng, state.view.lat], zoom: state.view.z, duration: 600 });
  }

  if (state.scope) {
    restoreScopeFromHash(state.scope);
  } else if (selectedScope) {
    hideInfoPanel();
  }
}

// ── Entry point ───────────────────────────────────────────────────────────────
init();
