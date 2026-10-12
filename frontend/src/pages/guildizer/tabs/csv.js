// Tiny CSV export helper shared by the Guildizer tables (members, leaderboard,
// campaigns, ...). Quotes every cell so commas/quotes/newlines are safe, neutralises
// spreadsheet formulas (a cell starting with = + - @ tab or CR is prefixed with an
// apostrophe so Excel/Sheets show it as text instead of running it), and writes a
// UTF-8 BOM so Excel reads non-ASCII names correctly.
const NUMBER = /^[+-]?\d+(\.\d+)?$/;

export function csvCell(v) {
  let s = String(v ?? '');
  // Plain numbers (including negatives) are data, not formulas.
  if (/^[=+\-@\t\r]/.test(s) && !NUMBER.test(s)) s = `'${s}`;
  return `"${s.replace(/"/g, '""')}"`;
}

export function downloadCsv(filename, headers, rows) {
  const lines = [headers.map(csvCell).join(','), ...rows.map((r) => r.map(csvCell).join(','))];
  const blob = new Blob(['\ufeff' + lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
