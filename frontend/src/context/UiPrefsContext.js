import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import { uiPrefs as uiPrefsApi } from '../services/api';

// Holds the open/closed state of every collapsible settings card, keyed by a
// stable card id. State is loaded from the backend on mount and saved (debounced)
// on every toggle, so a card the user collapses stays collapsed across refreshes
// and devices. A card is open ONLY if its id is stored as true — absent ids are
// closed by default.
const UiPrefsContext = createContext(null);

const NOOP = {
  ready: true,
  isOpen: (_id, def = false) => def,
  toggle: () => {},
};

export function useUiPrefs() {
  return useContext(UiPrefsContext) || NOOP;
}

export function UiPrefsProvider({ children }) {
  const [cards, setCards] = useState({});
  const [ready, setReady] = useState(false);
  const saveTimer = useRef(null);
  const latest = useRef({});

  useEffect(() => {
    let alive = true;
    uiPrefsApi
      .get()
      .then((res) => {
        const c = (res && res.data && res.data.cards) || {};
        if (alive) {
          latest.current = c;
          setCards(c);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (alive) setReady(true);
      });
    return () => {
      alive = false;
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, []);

  const scheduleSave = useCallback((next) => {
    latest.current = next;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      uiPrefsApi.update({ cards: latest.current }).catch(() => {});
    }, 600);
  }, []);

  const isOpen = useCallback(
    (id, def = false) => (id in cards ? !!cards[id] : def),
    [cards]
  );

  const toggle = useCallback(
    (id, def = false) => {
      setCards((prev) => {
        const cur = id in prev ? !!prev[id] : def;
        const next = { ...prev, [id]: !cur };
        scheduleSave(next);
        return next;
      });
    },
    [scheduleSave]
  );

  return (
    <UiPrefsContext.Provider value={{ ready, isOpen, toggle }}>
      {children}
    </UiPrefsContext.Provider>
  );
}

export default UiPrefsContext;
