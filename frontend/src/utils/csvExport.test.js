import { asText, buildCsv, csvCell, exportFilename } from './csvExport';

describe('csvExport', () => {
  test('neutralises spreadsheet formulas in user text', () => {
    expect(csvCell('=HYPERLINK("http://x")')).toBe('"\'=HYPERLINK(""http://x"")"');
    expect(csvCell('+1 555')).toBe('"\'+1 555"');
    expect(csvCell('@admin')).toBe('"\'@admin"');
    expect(csvCell('-cmd')).toBe('"\'-cmd"');
  });

  test('leaves plain numbers and numeric strings alone', () => {
    expect(csvCell(-5)).toBe('"-5"');
    expect(csvCell('-100123')).toBe('"-100123"');
    expect(csvCell(0)).toBe('"0"');
  });

  test('escapes quotes, keeps Unicode (Urdu) and newlines', () => {
    expect(csvCell('say "hi"')).toBe('"say ""hi"""');
    expect(csvCell('سلام دنیا')).toBe('"سلام دنیا"');
    expect(csvCell('a\nb')).toBe('"a\nb"');
  });

  test('identifiers keep leading zeros and full precision', () => {
    expect(csvCell(asText('000123'))).toBe('"=""000123"""');
    expect(csvCell(asText('1234567890123456789'))).toBe('"=""1234567890123456789"""');
    expect(csvCell(asText('0xAB'))).toBe('"0xAB"');
  });

  test('rows are CRLF separated and booleans are readable', () => {
    expect(buildCsv(['a', 'b'], [[true, null]])).toBe('"a","b"\r\n"Yes",""');
  });

  test('filename carries group, type and date', () => {
    expect(exportFilename('RupChain Community', 'members', '7d')).toMatch(/^rupchain-community_members_7d_\d{4}-\d{2}-\d{2}\.csv$/);
  });
});
