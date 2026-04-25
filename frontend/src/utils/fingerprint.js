/**
 * Lightweight, privacy-friendly device fingerprint generator.
 *
 * Uses only non-invasive, stable browser signals. No canvas fingerprinting,
 * no font enumeration, no storage probing. The output is a hex string derived
 * via FNV-1a hash over the concatenated signals — it cannot be reversed to
 * recover any individual signal value.
 *
 * The backend further SHA-256s the received hash before storage, so the raw
 * signal values are never persisted anywhere.
 */

/** FNV-1a 32-bit hash over a string — pure JS, no dependencies. */
function _fnv1a(str) {
  let hash = 2166136261; // FNV offset basis
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    // Multiply by FNV prime (16777619), kept within 32-bit unsigned range
    hash = (hash * 16777619) >>> 0;
  }
  return hash.toString(16).padStart(8, '0');
}

/**
 * Collect stable, non-invasive browser signals and return a hex fingerprint.
 * Safe to call synchronously — no async APIs used.
 */
export function generateFingerprint() {
  try {
    const signals = [
      navigator.userAgent || '',
      `${window.screen.width}x${window.screen.height}`,
      String(window.screen.colorDepth || 0),
      navigator.language || navigator.userLanguage || '',
      (() => {
        try { return Intl.DateTimeFormat().resolvedOptions().timeZone; }
        catch { return ''; }
      })(),
      navigator.platform || '',
      String(navigator.maxTouchPoints > 0 ? 1 : 0),
      String(navigator.hardwareConcurrency || 0),
      // Pixel ratio — differs between HiDPI/Retina and regular displays
      String(Math.round((window.devicePixelRatio || 1) * 10)),
    ];

    const raw = signals.join('|');
    return _fnv1a(raw);
  } catch {
    // Fallback: return a random value so registration still works
    return Math.random().toString(16).slice(2, 10);
  }
}
