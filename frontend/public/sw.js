/* Telegizer Service Worker
 * v5 — navigation requests always go to network (network-first).
 * Static hashed assets (/static/*) use cache-first.
 * index.html is intentionally NOT precached — it must always be fetched fresh
 * so new deployments are picked up immediately by Telegram WebView and browsers.
 *
 * Changes in v5:
 * - Never intercept POST requests or /api/* (unchanged)
 * - Always bypass auth routes: /forgot-password, /reset-password, /login, /register
 * - Fixed: caches.match() can return undefined — always fall back to a real Response
 *   so respondWith() never receives a non-Response value (was causing TypeError)
 */
const CACHE_VERSION = 'Telegizer-v5';
const STATIC_CACHE  = `${CACHE_VERSION}-static`;

// Only precache the offline fallback page — NOT index.html.
const PRECACHE_ASSETS = ['/offline.html', '/manifest.json'];

// Auth and password-flow pages must never be served from cache.
const BYPASS_PATHS = [
  '/forgot-password',
  '/reset-password',
  '/login',
  '/register',
  '/verify-email',
];

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

  // Always bypass SW for non-GET requests (POST, PUT, DELETE, etc.)
  if (request.method !== 'GET') return;

  // Always bypass API requests — never cache or intercept them.
  if (url.pathname.startsWith('/api/')) return;

  // Bypass auth/password-flow pages — must always be fresh from network.
  if (BYPASS_PATHS.some((p) => url.pathname.startsWith(p))) return;

  // ── Navigation requests (HTML pages incl. index.html) → NETWORK-FIRST ──────
  // Falls back to offline.html if the network is unreachable.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => response)
        .catch(async () => {
          const cached = await caches.match('/offline.html');
          return cached || new Response(
            '<h1>You are offline</h1>',
            { status: 503, headers: { 'Content-Type': 'text/html' } }
          );
        })
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

  // ── Other same-origin GET assets (icons, fonts, manifest) → NETWORK-FIRST ───
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
        .catch(async () => {
          // Return cached version if available; otherwise a safe 503 fallback.
          // Never pass undefined to respondWith() — that causes a TypeError.
          const cached = await caches.match(request);
          return cached || new Response('', { status: 503 });
        })
    );
  }
});
