// Keep tests hermetic: the app is served locally; everything else is stubbed.
async function isolate(page) {
  await page.route(/^https?:\/\/(?!127\.0\.0\.1|localhost)/, (route) => {
    const url = route.request().url();
    // The API is stubbed (see below) so the app does not mistake a blocked network for being offline.
    if (/\/api\//.test(url)) {
      const origin = route.request().headers().origin || 'http://127.0.0.1:4173';
      const cors = {
        'access-control-allow-origin': origin,
        'access-control-allow-credentials': 'true',
        'access-control-allow-headers': '*',
        'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
      };
      if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers: cors });
      // Logged out: auth endpoints say 401; /api/health must be 200 or the connection
      // monitor concludes the backend is down; everything else gets an empty object.
      const out = /\/api\/auth\//.test(url) ? { status: 401, body: '{"error":"unauthorized"}' }
        : /\/api\/health/.test(url) ? { status: 200, body: '{"status":"ok"}' }
        : { status: 200, body: '{}' };
      return route.fulfill({ ...out, contentType: 'application/json', headers: cors });
    }
    return route.abort();
  });
}

const PUBLIC_ROUTES = [
  '/', '/echo', '/guildizer-landing', '/pricing', '/terms', '/privacy',
  '/acceptable-use', '/contact', '/about', '/status', '/login', '/register', '/forgot-password',
];

module.exports = { isolate, PUBLIC_ROUTES };
