import { isChunkLoadError } from './ErrorBoundary';

describe('isChunkLoadError', () => {
  it.each([
    ['ChunkLoadError', 'Loading chunk 123 failed.'],
    ['Error', 'Failed to fetch dynamically imported module: https://x/y.js'],
    ['TypeError', 'Importing a module script failed.'],
    ['Error', 'Loading CSS chunk 5 failed'],
  ])('treats %s "%s" as a load failure', (name, message) => {
    expect(isChunkLoadError({ name, message })).toBe(true);
  });

  it.each([
    [new TypeError("Cannot read properties of undefined (reading 'map')")],
    [new Error('boom')],
    [null],
    [undefined],
  ])('does not treat real bugs as load failures', (err) => {
    expect(isChunkLoadError(err)).toBe(false);
  });
});
