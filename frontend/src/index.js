import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';

// Analytics (PostHog + GA4) is intentionally NOT initialized here.
// Both are initialized lazily in their respective init functions below,
// which are only called after the user explicitly accepts analytics in
// the CookieConsent banner. This ensures no tracking before consent — GDPR compliant.

export function initGA() {
  const GA_ID = process.env.REACT_APP_GA_MEASUREMENT_ID;
  if (!GA_ID || GA_ID === 'G-PLACEHOLDER') return;
  if (window.__ga_initialized) return;

  const script = document.createElement('script');
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${GA_ID}`;
  document.head.appendChild(script);

  window.dataLayer = window.dataLayer || [];
  window.gtag = function gtag() { window.dataLayer.push(arguments); };
  window.gtag('js', new Date());
  // send_page_view: false — we fire page_view manually on each route change
  window.gtag('config', GA_ID, { send_page_view: false, anonymize_ip: true });

  window.__ga_initialized = true;
  window.__ga_id = GA_ID;
}

export function trackGAPageView(path) {
  if (!window.__ga_initialized || !window.gtag) return;
  window.gtag('event', 'page_view', { page_path: path });
}

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
