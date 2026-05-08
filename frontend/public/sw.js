/* Telegizer Service Worker
 * v4 — navigation requests always go to network (network-first).
 * Static hashed assets (/static/*) use cache-first.
 * index.html is intentionally NOT precached — it must always be fetched fresh
 * so new deployments are picked up immediately by Telegram WebView and browsers.
 */
const CACHE_VERSION = 'Telegizer-v4';
const STATIC_CACHE  = `${CACHE_VERSION}-static`;

// Only precache the offline fallback page — NOT index.html.
const PRECACHE_ASSETS = ['/offline.html', '/manifest.json'];

// ── Install: precache offline fallback only ───────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE_ASSETS))
  );
  // Activate immediately — don't wait for old SW clients to unload.
  self.skipWaiting();
});

// ── Activate: delete ALL old caches ──────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== STATIC_CACHE)
          .map((k) => {
            console.log('[SW] Deleting old cache:', k);
            return caches.delete(k);
          })
      )
    )
  );
  // Take control of all open clients immediately.
  self.clients.claim();
});

// ── Fetch ─────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Always bypass SW for non-GET and API requests.
  if (request.method !== 'GET' || url.pathname.startsWith('/api/')) return;

  // ── Navigation requests (HTML pages incl. index.html) → NETWORK-FIRST ──────
  // This is the critical fix: new deployments are served immediately.
  // Falls back to offline.html if the network is unreachable.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Don't cache HTML responses — always keep them fresh.
          return response;
        })
        .catch(() => caches.match('/offline.html'))
    );
    return;
  }

  // ── Hashed static assets (/static/js/*, /static/css/*) → CACHE-FIRST ───────
  // CRA produces content-hashed filenames, so cache-forever is safe.
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(STATIC_CACHE).then((cache) => cache.put(request, clone));
          }
          return response;
        });
      })
    );
    return;
  }

  // ── Other same-origin assets (icons, fonts) → NETWORK-FIRST ─────────────────
  if (url.origin === self.location.origin) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(STATIC_CACHE).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(() => caches.match(request))
    );
  }
});
