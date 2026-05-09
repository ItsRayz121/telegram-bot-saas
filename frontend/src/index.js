import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';

// PostHog is intentionally NOT initialized here.
// It is initialized lazily in initPostHog() below, which is only called
// after the user explicitly accepts analytics in the CookieConsent banner.
// This ensures no tracking occurs before consent — GDPR compliant.

export function initPostHog() {
  const POSTHOG_KEY  = process.env.REACT_APP_POSTHOG_KEY;
  const POSTHOG_HOST = process.env.REACT_APP_POSTHOG_HOST || 'https://us.i.posthog.com';

  if (!POSTHOG_KEY || POSTHOG_KEY === 'phc_placeholder') return;
  if (window.__posthog_initialized) return;

  import('posthog-js').then(({ default: posthog }) => {
    posthog.init(POSTHOG_KEY, {
      api_host: POSTHOG_HOST,
      autocapture: false,
      capture_pageview: true,
      persistence: 'localStorage',
      loaded: (ph) => {
        if (process.env.NODE_ENV === 'development') ph.opt_out_capturing();
      },
    });
    window.__posthog_initialized = true;
  }).catch(() => {});
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
