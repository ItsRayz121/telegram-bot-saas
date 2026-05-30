import { useState, useEffect } from 'react';

const VARIANTS = {
  echo:      'Echo',
  assistant: 'AI Assistant',
};

function readFlag() {
  try {
    const v = window.posthog?.getFeatureFlag?.('assistant-name');
    return VARIANTS[v] ?? 'Echo';
  } catch {
    return 'Echo';
  }
}

export default function useAssistantName() {
  const [name, setName] = useState(readFlag);

  useEffect(() => {
    if (!window.posthog) return;
    const unsub = window.posthog.onFeatureFlags(() => setName(readFlag()));
    return () => { try { unsub?.(); } catch {} };
  }, []);

  return name;
}
