// Reliable, synchronous detection of a Telegram Mini App launch.
//
// Why not just check window.Telegram.WebApp.initData?
//   - The Telegram SDK script loads async and may not be ready at first render.
//   - Telegram's Android WebView often omits "Telegram" from the User-Agent, so a
//     UA-gated SDK loader never runs and window.Telegram stays undefined.
//
// The dependable signal is the launch hash: Telegram appends
//   #tgWebAppData=...&tgWebAppVersion=...&tgWebAppPlatform=...
// to the URL on EVERY Mini App open, before any script runs. index.html captures
// this into window.__IS_TELEGRAM__ on load (before the SDK can strip the hash).
export function isTelegramMiniApp() {
  try {
    if (window.__IS_TELEGRAM__) return true;
    if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData) return true;
    const h = window.location.hash || '';
    const s = window.location.search || '';
    if (h.indexOf('tgWebAppData') !== -1 || s.indexOf('tgWebAppData') !== -1) return true;
  } catch (e) {
    /* window/location unavailable — treat as non-Telegram */
  }
  return false;
}
