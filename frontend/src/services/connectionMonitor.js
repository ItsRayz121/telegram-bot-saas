// Single shared connection monitor. Nothing polls while the app is healthy:
// probes only start when a real signal suggests trouble (browser offline event,
// a network-level API failure, a 502/503/504, or repeated very slow responses).
//
// status: 'ok' | 'unstable' | 'offline' | 'backend_down'
// `reconnecting` is true while a probe is in flight or the next one is scheduled.

const BASE_URL = process.env.REACT_APP_API_URL || '';
const PROBE_TIMEOUT_MS = 6000;
const SLOW_MS = 8000;
const SLOW_STRIKES = 3;
const SLOW_WINDOW_MS = 60000;
const BACKOFF_BASE_MS = 2000;
const BACKOFF_MAX_MS = 30000;
const MANUAL_COOLDOWN_MS = 3000;

let state = { status: 'ok', reconnecting: false, attempt: 0, since: Date.now(), recoveredAt: 0 };
const listeners = new Set();
let timer = null;
let slowHits = [];
let lastManual = 0;
let started = false;

const emit = (patch) => {
  state = { ...state, ...patch };
  listeners.forEach((l) => { try { l(); } catch {} });
};

export const subscribe = (l) => { listeners.add(l); return () => listeners.delete(l); };
export const getSnapshot = () => state;

const jitter = (ms) => ms * (0.75 + Math.random() * 0.5);
const isHidden = () => typeof document !== 'undefined' && document.visibilityState === 'hidden';

async function timedFetch(url) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), PROBE_TIMEOUT_MS);
  try {
    return await fetch(url, { cache: 'no-store', signal: ctrl.signal, credentials: 'omit' });
  } finally {
    clearTimeout(t);
  }
}

// Returns 'ok' | 'offline' | 'backend_down'. Evidence-based: the backend is only
// blamed if our own origin (static host) is reachable, i.e. the user's network works.
async function probe() {
  try {
    const res = await timedFetch(`${BASE_URL}/api/health?_=${Date.now()}`);
    return res.ok ? 'ok' : 'backend_down';
  } catch {
    if (typeof navigator !== 'undefined' && navigator.onLine === false) return 'offline';
    try {
      const own = await timedFetch(`/manifest.json?_probe=${Date.now()}`);
      return own.ok ? 'backend_down' : 'offline';
    } catch {
      return 'offline';
    }
  }
}

function clearTimer() { if (timer) { clearTimeout(timer); timer = null; } }

function schedule() {
  clearTimer();
  if (state.status === 'ok') return;
  const delay = jitter(Math.min(BACKOFF_MAX_MS, BACKOFF_BASE_MS * 2 ** Math.min(state.attempt, 4)));
  emit({ reconnecting: true });
  timer = setTimeout(() => { timer = null; check(); }, delay);
}

export async function check() {
  if (isHidden() && state.status !== 'ok') return; // resumes on visibilitychange
  if (state.checking) return;
  state = { ...state, checking: true };
  const result = await probe();
  state = { ...state, checking: false };
  if (result === 'ok') {
    const wasBad = state.status === 'offline' || state.status === 'backend_down';
    clearTimer();
    slowHits = [];
    emit({ status: 'ok', reconnecting: false, attempt: 0, since: Date.now(), recoveredAt: wasBad ? Date.now() : state.recoveredAt });
    return;
  }
  emit({ status: result, attempt: state.attempt + 1, since: state.status === result ? state.since : Date.now() });
  schedule();
}

// Manual "Try again": a real probe, rate-limited.
export async function tryAgain() {
  const now = Date.now();
  if (now - lastManual < MANUAL_COOLDOWN_MS || state.checking) return;
  lastManual = now;
  clearTimer();
  emit({ reconnecting: true });
  await check();
}

// Called from the axios interceptors. Cheap and synchronous.
export function reportRequest({ networkError, status, durationMs, canceled }) {
  if (canceled) return;
  if (networkError || status === 502 || status === 503 || status === 504) {
    if (state.status === 'ok' || state.status === 'unstable') {
      if (!state.checking) check();
    }
    return;
  }
  if (typeof durationMs === 'number' && durationMs > SLOW_MS) {
    const now = Date.now();
    slowHits = slowHits.filter((t) => now - t < SLOW_WINDOW_MS).concat(now);
    if (slowHits.length >= SLOW_STRIKES && state.status === 'ok') {
      emit({ status: 'unstable', since: now });
    }
  } else if (state.status === 'unstable' && typeof durationMs === 'number' && durationMs < SLOW_MS / 2) {
    slowHits = [];
    emit({ status: 'ok', since: Date.now() });
  }
}

export function startConnectionMonitor() {
  if (started || typeof window === 'undefined') return;
  started = true;
  window.addEventListener('offline', () => {
    clearTimer();
    emit({ status: 'offline', attempt: 0, since: Date.now() });
    schedule();
  });
  // 'online' is only a hint — verify with a real probe before claiming recovery.
  window.addEventListener('online', () => { if (state.status !== 'ok') { clearTimer(); check(); } });
  document.addEventListener('visibilitychange', () => {
    if (isHidden()) { clearTimer(); return; }
    if (state.status !== 'ok') check();
  });
  if (navigator.onLine === false) {
    emit({ status: 'offline', since: Date.now() });
    schedule();
  }
}
