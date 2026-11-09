// "Open in Google Sheets" + "Refresh sheet" for any campaign submissions table.
// Real export via utils/googleSheets (Sheets API). Honest about being a snapshot.
import React, { useState } from 'react';
import { Button, CircularProgress, Tooltip, Typography, Box } from '@mui/material';
import { toast } from 'react-toastify';
import { exportToGoogleSheet, getLinkedSheet } from '../utils/googleSheets';

// Official Google Sheets mark (inline SVG, no external asset).
export const SheetsIcon = (props) => (
  <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true" {...props}>
    <path fill="#0F9D58" d="M30 4H12a4 4 0 0 0-4 4v32a4 4 0 0 0 4 4h24a4 4 0 0 0 4-4V14L30 4z" />
    <path fill="#87CEAC" d="M30 4v10h10L30 4z" />
    <path fill="#fff" d="M15 22v14h18V22H15zm7 12h-5v-3h5v3zm0-5h-5v-3h5v3zm9 5h-7v-3h7v3zm0-5h-7v-3h7v3z" />
  </svg>
);

/**
 * Props:
 *  - storageKey: unique per platform+scope+campaign (e.g. "tg:official:45:22")
 *  - title: spreadsheet title
 *  - build: () => ({ headers, rows })  complete dataset to write
 *  - disabled
 */
export default function GoogleSheetsButton({ storageKey, title, build, disabled }) {
  const [busy, setBusy] = useState(false);
  const [linked, setLinked] = useState(() => getLinkedSheet(storageKey));

  const run = async (refresh) => {
    // Open the tab synchronously (inside the click) so popup blockers allow it.
    const tab = refresh ? null : window.open('', '_blank');
    if (tab) { try { tab.document.title = 'Opening Google Sheets…'; tab.opener = null; } catch { /* cross-origin */ } }
    setBusy(true);
    try {
      const { headers, rows } = build();
      const res = await exportToGoogleSheet({ storageKey, title, headers, rows, refresh });
      setLinked(getLinkedSheet(storageKey));
      if (tab) tab.location.href = res.url;
      toast.success(res.created ? `Created Google Sheet (${res.rowCount} rows)`
        : refresh ? `Sheet refreshed (${res.rowCount} rows)` : 'Opened your existing Google Sheet');
    } catch (e) {
      if (tab) tab.close();
      toast.error(e.message || 'Google Sheets export failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
      <Button size="small" onClick={() => run(false)} disabled={disabled || busy}
        startIcon={busy ? <CircularProgress size={14} /> : <SheetsIcon />}>
        Open in Google Sheets
      </Button>
      {linked && (
        <>
          <Button size="small" onClick={() => run(true)} disabled={disabled || busy}>Refresh Sheet</Button>
          <Tooltip title="A snapshot copy in your own Google account. It does NOT update automatically — use Refresh Sheet to re-export the latest submissions.">
            <Typography variant="caption" color="text.secondary" sx={{ cursor: 'help' }}>
              Snapshot · {new Date(linked.exportedAt).toLocaleString()}
            </Typography>
          </Tooltip>
        </>
      )}
    </Box>
  );
}
