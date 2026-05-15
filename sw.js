/**
 * sw.js — Service Worker para a PWA CED Map
 * Estratégia: Cache-first para assets estáticos, Network-first para dados.
 */

const CACHE_VERSION = 'ced-map-v1';
const CACHE_STATIC  = `${CACHE_VERSION}-static`;
const CACHE_DATA    = `${CACHE_VERSION}-data`;

const STATIC_ASSETS = [
  './',
  './index.html',
  './style.css',
  './js/app.js',
  './manifest.json',
];

const DATA_ASSETS = [
  './data/banco.json',
  './data/ne_110m_countries.geojson',
  './data/ne_10m_admin1_slim.geojson',
];

// ── Install: pré-cachear assets estáticos ────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_STATIC).then(cache =>
      cache.addAll(STATIC_ASSETS.map(url => new Request(url, { cache: 'reload' })))
    )
  );
  // Não chamamos skipWaiting() — o SW só ativa na próxima navegação,
  // evitando que clients.claim() force um re-carregamento da página atual.
});

// ── Activate: limpar caches antigos ──────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k.startsWith('ced-map-') && k !== CACHE_STATIC && k !== CACHE_DATA)
          .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ── Fetch: estratégia híbrida ─────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Ignorar requisições externas (MapLibre CDN, tiles, etc.)
  if (url.origin !== location.origin) return;

  // Dados: Network-first (manter banco atualizado)
  if (DATA_ASSETS.some(a => url.pathname.endsWith(a.replace('./', '/')))) {
    event.respondWith(networkFirst(event.request, CACHE_DATA));
    return;
  }

  // Estáticos: Cache-first
  event.respondWith(cacheFirst(event.request, CACHE_STATIC));
});

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('Offline', { status: 503 });
  }
}

async function networkFirst(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached ?? new Response('Offline', { status: 503 });
  }
}
