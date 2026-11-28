// Vitest setup (jsdom). Kept minimal: the suites render with react-dom directly, not Testing Library.
// jsdom has no matchMedia; tests that care about it stub their own.
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false, media: query, onchange: null,
    addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent() { return false; },
  });
}
