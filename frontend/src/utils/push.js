// Web Push + notification sound helpers for Telegizer.
//
// Push relies on the service worker registered in App.js (production only).
// Everything here degrades gracefully: if the browser lacks support, or VAPID
// is not configured on the backend, the functions resolve to a falsy/empty
// result instead of throwing.
import { notifications as notificationsApi } from '../services/api';

export function pushSupported() {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

export function notificationPermission() {
  if (typeof Notification === 'undefined') return 'unsupported';
  return Notification.permission; // 'default' | 'granted' | 'denied'
}

// Convert a base64url VAPID public key to the Uint8Array the PushManager wants.
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = window.atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

async function getRegistration() {
  if (!('serviceWorker' in navigator)) return null;
  try {
    // Wait for the SW registered in App.js. In dev (no SW) this never resolves,
    // so race it against a registration lookup that returns undefined quickly.
    const existing = await navigator.serviceWorker.getRegistration();
    if (existing) return existing;
    return await navigator.serviceWorker.ready;
  } catch {
    return null;
  }
}

// Request OS permission, subscribe via PushManager, and persist to the backend.
// Returns true on success. Throws with a user-friendly message on hard failure.
//
// `api` is the notifications client to register with (vapidKey / subscribePush /
// unsubscribePush). Defaults to the main Telegizer client; the Guildizer page
// passes its own client. Because Guildizer shares this origin's service worker
// (and a SHARED VAPID keypair), an existing subscription is reused as-is and
// simply re-registered with whichever backend is enabling push.
export async function enablePush(api = notificationsApi) {
  if (!pushSupported()) {
    throw new Error('Push notifications are not supported on this device/browser.');
  }
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') {
    throw new Error('Notification permission was not granted.');
  }

  let keyRes;
  try {
    keyRes = await api.vapidKey();
  } catch {
    throw new Error('Could not reach the server to set up push.');
  }
  const publicKey = keyRes?.data?.public_key;
  if (!publicKey) {
    throw new Error('Push is not configured on the server yet.');
  }

  const reg = await getRegistration();
  if (!reg) {
    throw new Error('Service worker is not available. Install the app or reload, then try again.');
  }

  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey),
    });
  }
  await api.subscribePush(sub.toJSON());
  return true;
}

// Unsubscribe on the backend. Only drops the local browser subscription when
// `dropLocal` is true — Guildizer should not tear down the shared subscription
// that Telegizer push may still rely on (just deregister server-side).
// dropLocal defaults to false: the browser push subscription is shared across
// the Telegizer + Guildizer pillars (same origin, same VAPID key), so we only
// deregister server-side and leave the (harmless) browser subscription intact.
export async function disablePush(api = notificationsApi, { dropLocal = false } = {}) {
  let endpoint = null;
  try {
    const reg = await getRegistration();
    if (reg) {
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        endpoint = sub.endpoint;
        if (dropLocal) await sub.unsubscribe();
      }
    }
  } catch {
    /* ignore — still tell the backend to drop subs */
  }
  try {
    await api.unsubscribePush(endpoint ? { endpoint } : {});
  } catch {
    /* best effort */
  }
  return true;
}

// ── In-app bell sound ─────────────────────────────────────────────────────────
// Synthesized two-tone "ding" via Web Audio — no binary asset, works offline.
let _audioCtx = null;
export function playBellSound() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    if (!_audioCtx) _audioCtx = new Ctx();
    const ctx = _audioCtx;
    if (ctx.state === 'suspended') ctx.resume().catch(() => {});
    const now = ctx.currentTime;
    // Two short bell partials (G5 then C6) with a quick decay.
    [[784, 0], [1047, 0.12]].forEach(([freq, offset]) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, now + offset);
      gain.gain.exponentialRampToValueAtTime(0.18, now + offset + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + offset + 0.45);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now + offset);
      osc.stop(now + offset + 0.5);
    });
  } catch {
    /* audio not available — silent fallback */
  }
}
