/*
 * Telegram Mini App boot script — MUST load synchronously in <head> before the
 * React bundle and before the Telegram SDK.
 *
 * Self-hosted (instead of inline in index.html) so the production CSP
 * (script-src 'self' ...) allows it — an inline script is blocked without
 * 'unsafe-inline'/hashes, which silently broke Mini App detection.
 *
 * Captures the launch state SYNCHRONOUSLY from the URL hash (#tgWebAppData=...),
 * which Telegram appends on every Mini App open BEFORE any SDK runs. This is
 * reliable even when the User-Agent lacks "Telegram" (common on Android WebView)
 * or the SDK is slow to load. window.__IS_TELEGRAM__ / window.__TG_INIT_DATA__
 * are then read by the React app to redirect Mini App users straight to TMA auth.
 */
(function () {
  try {
    var h = window.location.hash || '';
    var s = window.location.search || '';
    window.__IS_TELEGRAM__ =
      h.indexOf('tgWebAppData') !== -1 || s.indexOf('tgWebAppData') !== -1;
    // Capture the raw initData SYNCHRONOUSLY from the launch hash, before the
    // SDK loads (and possibly rewrites the URL). tgWebAppData's value IS the
    // initData string (URLSearchParams decodes it once). This lets auth proceed
    // even if telegram-web-app.js is slow or fails to load (e.g. VPN / 2G).
    var src = h.indexOf('tgWebAppData') !== -1 ? h.replace(/^#/, '') : s.replace(/^\?/, '');
    window.__TG_INIT_DATA__ = src ? (new URLSearchParams(src).get('tgWebAppData') || null) : null;
  } catch (e) { window.__IS_TELEGRAM__ = false; window.__TG_INIT_DATA__ = null; }
  // Load the SDK if this is a Mini App launch (by hash) or the UA hints Telegram.
  // Harmless no-op for regular browsers.
  var uaTelegram = navigator.userAgent && /Telegram/i.test(navigator.userAgent);
  if (window.__IS_TELEGRAM__ || uaTelegram) {
    var _tgScript = document.createElement('script');
    _tgScript.src = 'https://telegram.org/js/telegram-web-app.js';
    document.head.appendChild(_tgScript);
  }
})();
