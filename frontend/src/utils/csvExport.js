// Shared CSV export helpers.
//
//  * UTF-8 with a BOM, so Excel opens Urdu / Arabic / emoji correctly.
//  * Every cell is quoted; quotes are doubled; rows end in CRLF.
//  * Spreadsheet formula injection is neutralised: user-controlled text that
//    starts with = + - @ (or a tab / CR) gets a leading apostrophe so Excel and
//    Sheets show it as text instead of evaluating it. Plain numbers are written
//    untouched, as are strings that are just a number.
//  * Identifiers (Telegram ids, UIDs, tx hashes) can be wrapped with asText() so
//    long digit strings and leading zeros survive the round trip through Excel.

const FORMULA_START = /^[=+\-@\t\r]/;
const PURE_NUMBER = /^-?\d+(\.\d+)?$/;

class TextCell {
  constructor(v) { this.v = v; }
}

/** Mark a value as an identifier that must stay text (keeps leading zeros / full precision). */
export const asText = (v) => new TextCell(v);

export function csvCell(value) {
  if (value instanceof TextCell) {
    const s = String(value.v ?? '');
    // digits-only identifiers: ="000123" is read as text by Excel/Sheets and cannot run code
    if (/^-?\d+$/.test(s)) return `"=""${s}"""`;
    return csvCell(s);
  }
  if (value === null || value === undefined) return '""';
  if (typeof value === 'number') return `"${Number.isFinite(value) ? value : ''}"`;
  if (typeof value === 'boolean') return `"${value ? 'Yes' : 'No'}"`;
  let s = String(value);
  if (FORMULA_START.test(s) && !PURE_NUMBER.test(s)) s = `'${s}`;
  return `"${s.replace(/"/g, '""')}"`;
}

export function buildCsv(headers, rows) {
  return [headers, ...rows].map((r) => r.map(csvCell).join(',')).join('\r\n');
}

export function downloadCsv(filename, headers, rows) {
  const blob = new Blob(['﻿', buildCsv(headers, rows)], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const slug = (s) => String(s || '').normalize('NFKD').replace(/[^\w]+/g, '-').replace(/^-+|-+$/g, '').toLowerCase().slice(0, 40);

/** e.g. exportFilename('RupChain Community', 'members', '7d') -> rupchain-community_members_7d_2026-10-10.csv */
export function exportFilename(...parts) {
  const date = new Date().toISOString().slice(0, 10);
  return `${parts.map(slug).filter(Boolean).join('_')}_${date}.csv`;
}

/**
 * Walks every page of a paginated endpoint so an export covers ALL matching rows,
 * not just the page on screen. fetchPage(page) -> { rows, pages }.
 */
export async function fetchAllPages(fetchPage, { maxPages = 200, onProgress } = {}) {
  const out = [];
  let page = 1;
  let pages = 1;
  do {
    // eslint-disable-next-line no-await-in-loop
    const res = await fetchPage(page);
    out.push(...res.rows);
    pages = res.pages || 1;
    onProgress?.(page, pages, out.length);
    page += 1;
  } while (page <= pages && page <= maxPages);
  return { rows: out, truncated: pages > maxPages };
}
