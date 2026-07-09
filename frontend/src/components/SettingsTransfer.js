import React, { useState, useRef, useCallback } from 'react';
import {
  Box, Card, CardContent, Typography, Button, Alert, AlertTitle, Chip, Stack,
  Divider, CircularProgress, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Paper, Dialog, DialogTitle, DialogContent, DialogActions,
} from '@mui/material';
import {
  FileDownload, FileUpload, WorkspacePremium, LinkOff, CheckCircle,
} from '@mui/icons-material';
import { toast } from 'react-toastify';

const MAX_FILE_BYTES = 512 * 1024;

function formatValue(v) {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'boolean') return v ? 'On' : 'Off';
  if (Array.isArray(v)) return v.length ? `${v.length} item(s)` : 'empty';
  if (typeof v === 'object') return 'object';
  const s = String(v);
  return s.length > 60 ? `${s.slice(0, 60)}…` : s || '—';
}

/**
 * Import / Export of a board's bot configuration.
 *
 * Rendered by both Telegizer (group) and Guildizer (server) so the two boards
 * stay visually identical by construction. Everything platform-specific arrives
 * through props:
 *
 *   onExport()               -> Promise<envelope>
 *   onImport(file, dryRun)   -> Promise<{changes, skipped, bindings_excluded, source_group}>
 *   onImported(settings)     -> called after a successful apply, to refresh the parent
 *   scopeLabel               -> "group" | "server"
 *   fileStem                 -> basename for the downloaded file
 *   gatesOnFree              -> whether this board ever leaves Pro features off
 *                               on import (Telegizer yes; Guildizer never gates
 *                               these settings, so it passes false to hide the
 *                               speculative Free-plan warning)
 */
export default function SettingsTransfer({
  onExport,
  onImport,
  onImported,
  scopeLabel = 'group',
  fileStem = 'settings',
  isPaid = true,
  gatesOnFree = true,
}) {
  const [exporting, setExporting] = useState(false);
  const [preview, setPreview] = useState(null);   // dry-run result
  const [pendingFile, setPendingFile] = useState(null);
  const [checking, setChecking] = useState(false);
  const [applying, setApplying] = useState(false);
  const fileInputRef = useRef(null);

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      const { data } = await onExport();
      const meta = data.telegizer_settings_export || {};
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${fileStem}-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      const excluded = meta.bindings_excluded || [];
      toast.success(
        excluded.length
          ? `Settings exported. ${excluded.length} channel/admin link(s) left out.`
          : 'Settings exported.'
      );
    } catch (e) {
      toast.error(e?.response?.data?.error || 'Export failed.');
    } finally {
      setExporting(false);
    }
  }, [onExport, fileStem]);

  const handleFilePicked = useCallback(async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';       // allow re-picking the same file
    if (!file) return;

    if (file.size > MAX_FILE_BYTES) {
      toast.error('That file is too large to be a settings export.');
      return;
    }

    let parsed;
    try {
      parsed = JSON.parse(await file.text());
    } catch {
      toast.error("That file isn't valid JSON.");
      return;
    }

    setChecking(true);
    try {
      const { data } = await onImport(parsed, true);   // dry run
      setPendingFile(parsed);
      setPreview(data);
    } catch (e) {
      toast.error(e?.response?.data?.error || 'That file could not be read.');
    } finally {
      setChecking(false);
    }
  }, [onImport]);

  const handleApply = useCallback(async () => {
    if (!pendingFile) return;
    setApplying(true);
    try {
      const { data } = await onImport(pendingFile, false);
      toast.success(data.message || 'Settings imported.');
      setPreview(null);
      setPendingFile(null);
      onImported?.(data.settings);
    } catch (e) {
      toast.error(e?.response?.data?.error || 'Import failed.');
    } finally {
      setApplying(false);
    }
  }, [pendingFile, onImport, onImported]);

  const closePreview = () => {
    if (applying) return;
    setPreview(null);
    setPendingFile(null);
  };

  const changes = preview?.changes || [];
  const skipped = preview?.skipped || [];
  const bindings = preview?.bindings_excluded || [];

  return (
    <Box>
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>Export settings</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Download this {scopeLabel}'s configuration as a file you can keep as a backup,
            or send to someone else to import into their own {scopeLabel}.
          </Typography>

          <Alert severity="info" icon={<LinkOff fontSize="inherit" />} sx={{ mb: 2 }}>
            The file contains no API keys and no private data. Channel, topic and admin
            links are left out too, because they only mean something inside this {scopeLabel}.
          </Alert>

          <Button
            variant="contained"
            startIcon={exporting ? <CircularProgress size={16} color="inherit" /> : <FileDownload />}
            onClick={handleExport}
            disabled={exporting}
          >
            {exporting ? 'Exporting…' : 'Export settings'}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>Import settings</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Load a settings file into this {scopeLabel}. You'll see exactly what changes
            before anything is saved. Settings not present in the file are left as they are.
          </Typography>

          {!isPaid && gatesOnFree && (
            <Alert severity="warning" icon={<WorkspacePremium fontSize="inherit" />} sx={{ mb: 2 }}>
              You're on the Free plan. Any Pro features in the file will be imported but
              left switched off — upgrade to turn them on.
            </Alert>
          )}

          <input
            ref={fileInputRef}
            type="file"
            accept="application/json,.json"
            onChange={handleFilePicked}
            style={{ display: 'none' }}
          />
          <Button
            variant="outlined"
            startIcon={checking ? <CircularProgress size={16} /> : <FileUpload />}
            onClick={() => fileInputRef.current?.click()}
            disabled={checking}
          >
            {checking ? 'Reading file…' : 'Choose settings file'}
          </Button>
        </CardContent>
      </Card>

      <Dialog open={!!preview} onClose={closePreview} maxWidth="md" fullWidth>
        <DialogTitle>
          Review import
          {preview?.source_group ? (
            <Typography variant="body2" color="text.secondary">
              From “{preview.source_group}”
            </Typography>
          ) : null}
        </DialogTitle>

        <DialogContent dividers>
          {skipped.length > 0 && (
            <Alert severity="warning" icon={<WorkspacePremium fontSize="inherit" />} sx={{ mb: 2 }}>
              <AlertTitle>
                {skipped.length} feature{skipped.length > 1 ? 's need' : ' needs'} an upgrade
              </AlertTitle>
              <Typography variant="body2" sx={{ mb: 1 }}>
                These will be imported but left switched off. Upgrade and you can turn them
                on without setting them up again.
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {skipped.map((s) => (
                  <Chip
                    key={s.key}
                    size="small"
                    color={s.requires === 'enterprise' ? 'secondary' : 'warning'}
                    label={`${s.label} · ${s.requires === 'enterprise' ? 'Enterprise' : 'Pro'}`}
                  />
                ))}
              </Stack>
            </Alert>
          )}

          {bindings.length > 0 && (
            <Alert severity="info" icon={<LinkOff fontSize="inherit" />} sx={{ mb: 2 }}>
              <AlertTitle>{bindings.length} link(s) skipped</AlertTitle>
              <Typography variant="body2">
                The file referenced channels, topics or admins from another {scopeLabel}.
                This {scopeLabel}'s own settings for those are untouched.
              </Typography>
            </Alert>
          )}

          {changes.length === 0 ? (
            <Alert severity="success" icon={<CheckCircle fontSize="inherit" />}>
              {skipped.length > 0
                ? `Everything in this file that your plan allows is already applied. The ${
                    skipped.length > 1 ? 'features' : 'feature'} above ${
                    skipped.length > 1 ? 'need' : 'needs'} an upgrade before ${
                    skipped.length > 1 ? 'they' : 'it'} can be turned on.`
                : 'This file matches your current settings. Nothing would change.'}
            </Alert>
          ) : (
            <>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                {changes.length} setting{changes.length > 1 ? 's' : ''} will change
              </Typography>
              <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 360, overflowX: 'auto' }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      <TableCell>Setting</TableCell>
                      <TableCell>Now</TableCell>
                      <TableCell>After import</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {changes.map((c) => (
                      <TableRow key={c.path}>
                        <TableCell sx={{ fontFamily: 'monospace', fontSize: 12, whiteSpace: 'nowrap' }}>
                          {c.path}
                        </TableCell>
                        <TableCell sx={{ color: 'text.secondary' }}>{formatValue(c.from)}</TableCell>
                        <TableCell sx={{ fontWeight: 600 }}>{formatValue(c.to)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </>
          )}
        </DialogContent>

        <DialogActions>
          <Button onClick={closePreview} disabled={applying}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleApply}
            disabled={applying || changes.length === 0}
            startIcon={applying ? <CircularProgress size={16} color="inherit" /> : null}
          >
            {applying ? 'Importing…' : `Import ${changes.length} setting(s)`}
          </Button>
        </DialogActions>
      </Dialog>

      <Divider sx={{ mt: 3 }} />
    </Box>
  );
}
