import { useEffect } from 'react';

const DEFAULT_TITLE = 'Telegizer — Telegram Community Management Platform';
const DEFAULT_DESC =
  'Telegizer — Telegram group management platform. AutoMod, scheduled messages, ' +
  'member XP system, analytics, and AI auto-reply. Free plan available.';
const BASE_URL = 'https://telegizer.com';

/**
 * Per-route <title>, meta description and canonical URL.
 *
 * The app is a CRA SPA with a single static index.html, so without this every
 * route presents the identical title/description to crawlers and browser tabs.
 * Google renders JS, so client-side meta is picked up for indexing.
 *
 * Usage: usePageMeta('Pricing', 'Simple, transparent pricing…')
 * Pass no arguments to reset to the site defaults.
 */
export default function usePageMeta(title, description) {
  useEffect(() => {
    document.title = title ? `${title} | Telegizer` : DEFAULT_TITLE;

    const desc = document.querySelector('meta[name="description"]');
    if (desc) desc.setAttribute('content', description || DEFAULT_DESC);

    const canonical = document.querySelector('link[rel="canonical"]');
    if (canonical) {
      const path = window.location.pathname === '/' ? '/' : window.location.pathname;
      canonical.setAttribute('href', `${BASE_URL}${path}`);
    }

    return () => {
      document.title = DEFAULT_TITLE;
      if (desc) desc.setAttribute('content', DEFAULT_DESC);
      if (canonical) canonical.setAttribute('href', `${BASE_URL}/`);
    };
  }, [title, description]);
}
