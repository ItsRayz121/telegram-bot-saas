// Build-time entry: renders the homepage to static HTML (scripts/prerender.mjs runs this in Node).
// The browser still boots the full app with createRoot, which replaces this markup with the live page;
// the pre-rendered copy only exists so the first paint does not wait for the JavaScript bundle.
import React from 'react';
import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom';
import createCache from '@emotion/cache';
import { CacheProvider } from '@emotion/react';
import createEmotionServer from '@emotion/server/create-instance';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import theme from './theme';
import Landing from './pages/Landing';

export function render(url = '/') {
  // Same key as Emotion's default client cache, so the browser adopts these style tags instead of duplicating them.
  const cache = createCache({ key: 'css' });
  const { extractCriticalToChunks, constructStyleTagsFromChunks } = createEmotionServer(cache);
  const html = renderToString(
    <CacheProvider value={cache}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <StaticRouter location={url}>
          <Landing />
        </StaticRouter>
      </ThemeProvider>
    </CacheProvider>,
  );
  return { html, styles: constructStyleTagsFromChunks(extractCriticalToChunks(html)) };
}
