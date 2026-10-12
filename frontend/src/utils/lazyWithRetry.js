import React from 'react';

// React.lazy with one retry, then a single guarded page reload. A chunk fails to load when the user is
// mid-session across a deploy (old hashed file gone) or the network blipped; reloading once fetches the
// fresh index. The sessionStorage flag stops a reload loop if the chunk is genuinely unreachable (e.g.
// offline) - then the error reaches the ErrorBoundary instead.
const FLAG = 'tg_chunk_reload';

export default function lazyWithRetry(factory) {
  return React.lazy(async () => {
    try {
      return await factory();
    } catch (first) {
      await new Promise((r) => setTimeout(r, 400));
      try {
        return await factory();
      } catch (err) {
        let already = true;
        try { already = sessionStorage.getItem(FLAG) === '1'; } catch { /* storage unavailable */ }
        const online = typeof navigator === 'undefined' || navigator.onLine !== false;
        if (!already && online) {
          try { sessionStorage.setItem(FLAG, '1'); } catch { /* ignore */ }
          window.location.reload();
          return new Promise(() => {}); // page is reloading
        }
        throw err;
      }
    }
  });
}

// Called once the app has rendered successfully so a later deploy can reload again.
export function clearChunkReloadFlag() {
  try { sessionStorage.removeItem(FLAG); } catch { /* ignore */ }
}
