// Real Google Sheets export (no fake links).
//
// Flow: Google Identity Services token client (browser OAuth, narrow `drive.file`
// scope = the app can only touch spreadsheets it created) -> Sheets REST API.
// The access token lives in memory only (~1h) and is never sent to our servers.
// Data written is the complete authorised dataset the page already loaded from the
// permission-checked backend, so tenant boundaries are the same as the CSV export.
//
// The created spreadsheet id is remembered per campaign (localStorage) so a second
// click reopens / refreshes the SAME sheet instead of creating duplicates. It is a
// SNAPSHOT: nothing syncs automatically; "Refresh sheet" re-writes it on demand.
// The sheet is created private to the user's own Google account (never shared).

import { googleCalendar } from '../services/api';

const SCOPE = 'https://www.googleapis.com/auth/drive.file';
const GIS_SRC = 'https://accounts.google.com/gsi/client';
const SHEETS = 'https://sheets.googleapis.com/v4/spreadsheets';
const CHUNK = 2000; // rows per values.update call

let gisPromise = null;
let cachedToken = null; // { token, exp }
let cachedClientId = null;

function loadGis() {
  if (window.google?.accounts?.oauth2) return Promise.resolve();
  if (!gisPromise) {
    gisPromise = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = GIS_SRC; s.async = true;
      s.onload = () => resolve();
      s.onerror = () => { gisPromise = null; reject(new Error('Could not load Google sign-in (blocked by browser or network?)')); };
      document.head.appendChild(s);
    });
  }
  return gisPromise;
}

async function getClientId() {
  if (cachedClientId) return cachedClientId;
  const env = process.env.REACT_APP_GOOGLE_CLIENT_ID;
  if (env) { cachedClientId = env; return env; }
  try {
    const r = await googleCalendar.clientId();
    cachedClientId = r.data.client_id;
    return cachedClientId;
  } catch {
    throw new Error('Google is not configured on this server yet.');
  }
}

/** Warm the client id + Google script ahead of the click, so the consent popup opens
 *  inside the user gesture (a network wait before it would get the popup blocked). */
export function preloadGoogle() {
  getClientId().catch(() => {});
  loadGis().catch(() => {});
}

/** Resolve a short-lived access token, prompting Google consent only when needed. */
export async function getSheetsToken({ forcePrompt = false } = {}) {
  if (!forcePrompt && cachedToken && cachedToken.exp > Date.now() + 30000) return cachedToken.token;
  const [clientId] = await Promise.all([getClientId(), loadGis()]);
  return new Promise((resolve, reject) => {
    const client = window.google.accounts.oauth2.initTokenClient({
      client_id: clientId,
      scope: SCOPE,
      callback: (resp) => {
        if (resp.error || !resp.access_token) {
          reject(new Error(resp.error === 'access_denied'
            ? 'Google access was not granted.' : (resp.error_description || resp.error || 'Google authorization failed')));
          return;
        }
        cachedToken = { token: resp.access_token, exp: Date.now() + (Number(resp.expires_in) || 3600) * 1000 };
        resolve(resp.access_token);
      },
      error_callback: (err) => reject(new Error(err?.type === 'popup_closed' ? 'Google sign-in was closed.' : (err?.message || 'Google authorization failed'))),
    });
    client.requestAccessToken({ prompt: '' });
  });
}

async function gfetch(token, url, opts = {}) {
  const res = await fetch(url, {
    ...opts,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', ...(opts.headers || {}) },
  });
  if (!res.ok) {
    let msg = `Google Sheets error (${res.status})`;
    try { const j = await res.json(); msg = j?.error?.message || msg; } catch { /* keep default */ }
    const err = new Error(msg); err.status = res.status; throw err;
  }
  return res.status === 204 ? null : res.json();
}

// Cells starting with = + - @ would be evaluated as formulas; USER_ENTERED is used so
// numbers/dates parse, therefore neutralise text exactly like the CSV exporter does.
const safe = (v) => {
  if (v === null || v === undefined) return '';
  if (typeof v === 'number') return v;
  const s = String(v);
  return /^[=+\-@\t\r]/.test(s) && !/^-?\d+(\.\d+)?$/.test(s) ? `'${s}` : s;
};

async function writeValues(token, id, headers, rows) {
  const all = [headers, ...rows].map((r) => r.map(safe));
  // Wipe the sheet first so a refresh never leaves stale trailing rows.
  await gfetch(token, `${SHEETS}/${id}/values/A:ZZ:clear`, { method: 'POST', body: '{}' });
  for (let i = 0; i < all.length; i += CHUNK) {
    const part = all.slice(i, i + CHUNK);
    await gfetch(token,
      `${SHEETS}/${id}/values/A${i + 1}?valueInputOption=USER_ENTERED`,
      { method: 'PUT', body: JSON.stringify({ values: part }) });
  }
  // Bold + frozen header row, cosmetic only — failure must not fail the export.
  try {
    await gfetch(token, `${SHEETS}/${id}:batchUpdate`, {
      method: 'POST',
      body: JSON.stringify({ requests: [
        { repeatCell: { range: { sheetId: 0, startRowIndex: 0, endRowIndex: 1 }, cell: { userEnteredFormat: { textFormat: { bold: true } } }, fields: 'userEnteredFormat.textFormat.bold' } },
        { updateSheetProperties: { properties: { sheetId: 0, gridProperties: { frozenRowCount: 1 } }, fields: 'gridProperties.frozenRowCount' } },
      ] }),
    });
  } catch { /* cosmetic */ }
}

const key = (k) => `telegizer:sheet:${k}`;
export function getLinkedSheet(storageKey) {
  try { return JSON.parse(localStorage.getItem(key(storageKey)) || 'null'); } catch { return null; }
}
function setLinkedSheet(storageKey, v) {
  try { localStorage.setItem(key(storageKey), JSON.stringify(v)); } catch { /* storage unavailable */ }
}
export function forgetLinkedSheet(storageKey) {
  try { localStorage.removeItem(key(storageKey)); } catch { /* ignore */ }
}

/**
 * Create the spreadsheet (first time) or, with refresh=true, re-write the linked one.
 * Returns { id, url, created, exportedAt, rowCount }. Throws Error with a readable message.
 */
export async function exportToGoogleSheet({ storageKey, title, headers, rows, refresh = false }) {
  const linked = getLinkedSheet(storageKey);
  let token = await getSheetsToken();
  const run = async (t) => {
    if (linked?.id) {
      try {
        // Still ours and not deleted? (drive.file only sees files this app created.)
        const meta = await gfetch(t, `${SHEETS}/${linked.id}?fields=spreadsheetId,spreadsheetUrl`);
        if (refresh) await writeValues(t, linked.id, headers, rows);
        return { id: linked.id, url: meta.spreadsheetUrl, created: false };
      } catch (e) {
        if (e.status !== 404 && e.status !== 403) throw e;
        forgetLinkedSheet(storageKey); // deleted / not accessible with this Google account -> create anew
      }
    }
    const made = await gfetch(t, SHEETS, {
      method: 'POST',
      body: JSON.stringify({ properties: { title }, sheets: [{ properties: { title: 'Submissions' } }] }),
    });
    await writeValues(t, made.spreadsheetId, headers, rows);
    return { id: made.spreadsheetId, url: made.spreadsheetUrl, created: true };
  };
  let out;
  try { out = await run(token); } catch (e) {
    if (e.status === 401) { cachedToken = null; token = await getSheetsToken({ forcePrompt: true }); out = await run(token); } else throw e;
  }
  const result = { ...out, exportedAt: new Date().toISOString(), rowCount: rows.length };
  setLinkedSheet(storageKey, { id: result.id, url: result.url, exportedAt: result.exportedAt, rowCount: result.rowCount });
  return result;
}
