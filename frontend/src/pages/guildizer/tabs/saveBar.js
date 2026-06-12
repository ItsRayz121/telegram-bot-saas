import { createContext, useContext, useEffect, useRef } from 'react';

// Drives the single sticky "Save → Saved" button in the server-settings shell
// (Telegizer parity). Each editable tab registers its save handler + dirty/saving
// state here; the shell renders ONE Save button that reflects the active tab.
// When a tab is used standalone (no provider) the hook returns null and the tab
// falls back to rendering its own inline Save button.
export const SaveBarContext = createContext(null);

export function useSaveBar({ save, dirty = true, saving = false }) {
  const sb = useContext(SaveBarContext);
  const saveRef = useRef(save);
  saveRef.current = save;

  // Register the (ref-stable) save handler once per mount; clear on unmount so
  // switching subtabs hides the button until the next tab registers.
  useEffect(() => {
    if (!sb) return undefined;
    sb.register(() => saveRef.current && saveRef.current());
    return () => sb.unregister();
  }, [sb]);

  // Push dirty/saving up whenever they change (drives label + disabled state).
  useEffect(() => {
    if (sb) sb.report({ dirty, saving });
  }, [sb, dirty, saving]);

  return sb; // null → standalone, tab shows its own button
}
