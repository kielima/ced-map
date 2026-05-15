/**
 * sw.js — Service Worker para a PWA CED Map
 * Estratégia: Cache-first para assets estáticos, Network-first para dados.
 */

const CACHE_VERSION = 'ced-map-v4';
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
  './data/ne_50m_admin1_slim.geojson',
];

// ── Install: pré-cachear assets estáticos ────────────────────────────────────
self.addEventListener('install', event => {
  // skipWaiting força o SW novo a ativar imediatamente em vez de esperar
  // todas as abas controladas pelo SW antigo serem fechadas. Combinado com
  // clients.claim() no activate, garante que deploys propaguem na próxima
  // requisição — sem isso, usuários ficam presos em versão antiga até
  // fechar e reabrir todas as abas/PWAs.
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_STATIC).then(cache =>
      cache.addAll(STATIC_ASSETS.map(url => new Request(url, { cache: 'reload' })))
    )
  );
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

  // HTML / raiz: Network-first. Caso contrário um index.html cacheado
  // referenciando app.js?v=N antigo nunca é atualizado, e o usuário fica preso
  // em versão velha mesmo após deploys. Cai pro cache só se offline.
  if (url.pathname.endsWith('/') || url.pathname.endsWith('.html')) {
    event.respondWith(networkFirst(event.request, CACHE_STATIC));
    return;
  }

  // Demais estáticos (JS, CSS, ícones): Cache-first.
  // app.js?v=N tem query string distinta por versão, então cada deploy
  // resulta numa chave de cache nova e o cache-first não fica preso.
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
