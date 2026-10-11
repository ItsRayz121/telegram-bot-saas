import { useEffect, useRef } from 'react';
import { useLocation, useNavigationType } from 'react-router-dom';

/**
 * Remembers the window scroll position per history entry and puts it back when the
 * user returns with Back/Forward (POP). Fresh navigations (PUSH/REPLACE) start at the
 * top as before. `ready` must flip to true once the page has its content.
 */
export default function useScrollRestore(ready) {
  const { key } = useLocation();
  const navType = useNavigationType();
  const restored = useRef(false);
  const storeKey = `scroll:${key}`;

  useEffect(() => {
    let raf = 0;
    const save = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        try { sessionStorage.setItem(storeKey, String(window.scrollY)); } catch { /* storage unavailable */ }
      });
    };
    window.addEventListener('scroll', save, { passive: true });
    return () => {
      window.removeEventListener('scroll', save);
      cancelAnimationFrame(raf);
      try { sessionStorage.setItem(storeKey, String(window.scrollY)); } catch { /* storage unavailable */ }
    };
  }, [storeKey]);

  useEffect(() => {
    if (!ready || restored.current || navType !== 'POP') return;
    restored.current = true;
    let y = 0;
    try { y = Number(sessionStorage.getItem(storeKey)) || 0; } catch { /* storage unavailable */ }
    if (y > 0) requestAnimationFrame(() => window.scrollTo(0, y));
  }, [ready, navType, storeKey]);
}
