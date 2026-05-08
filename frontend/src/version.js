// Build-time constants injected via REACT_APP_* env vars.
// REACT_APP_BUILD_TIME is set by the build script (package.json).
export const APP_VERSION   = '2026-05-08-v1';
export const BUILD_TIME    = process.env.REACT_APP_BUILD_TIME || 'dev';
export const API_BASE_URL  = process.env.REACT_APP_API_URL   || '(same origin)';
export const IS_TELEGRAM   = !!(window?.Telegram?.WebApp?.initData);
