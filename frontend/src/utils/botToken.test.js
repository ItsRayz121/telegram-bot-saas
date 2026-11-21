import { tokenFormatHint } from './botToken';

test('accepts a well-formed token and stays quiet while empty', () => {
  expect(tokenFormatHint('')).toBe('');
  expect(tokenFormatHint('123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA')).toBe('');
});
test('explains the likely mistake', () => {
  expect(tokenFormatHint('hello')).toMatch(/does not look like/);
  expect(tokenFormatHint('123456789:short')).toMatch(/incomplete/);
  expect(tokenFormatHint('123 456:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA')).toMatch(/no spaces/);
});
