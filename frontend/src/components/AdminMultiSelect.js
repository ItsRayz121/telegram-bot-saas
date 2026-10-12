import React, { useMemo, useState } from 'react';
import {
  Avatar, Box, Button, Chip, CircularProgress, IconButton, InputAdornment, Popover,
  Stack, Switch, TextField, Tooltip, Typography,
} from '@mui/material';
import { Refresh, Search } from '@mui/icons-material';

/**
 * Searchable multi-select for group admins (chips + count + popover list).
 *
 * Shared by "Notify Admins" (report DMs) and "Admins who bypass smart moderation".
 * Selection is controlled by the caller and keyed by stable Telegram user ID, so
 * the two settings stay separate stored values.
 *
 * - Chips come from the SAVED ids, not from the loaded admin list: an id that is
 *   missing from the list (admin left, list not loaded yet, refresh failed) stays
 *   selected and is shown by id. A refresh never rewrites the selection.
 * - requireDm: when true, admins who have not started the bot cannot be newly
 *   selected (needed for DM delivery). Moderation bypass passes false: "started
 *   bot" is DM readiness only and is never a prerequisite there. An already-saved
 *   id can always be removed.
 */
export default function AdminMultiSelect({
  label,
  helperText,
  selectedIds = [],
  admins = [],
  loading = false,
  requireDm = false,
  onChange,
  onRefresh,
  buttonLabel = 'Select admins',
}) {
  const [anchor, setAnchor] = useState(null);
  const [query, setQuery] = useState('');

  const byId = useMemo(() => {
    const m = new Map();
    admins.forEach((a) => m.set(String(a.user_id), a));
    return m;
  }, [admins]);

  const selectedSet = useMemo(() => new Set(selectedIds.map(String)), [selectedIds]);

  const nameOf = (id) => {
    const a = byId.get(String(id));
    if (!a) return String(id);
    return a.username ? `@${a.username}` : (a.first_name || String(id));
  };

  const toggle = (admin) => {
    const id = admin.user_id;
    const isSel = selectedSet.has(String(id));
    if (isSel) onChange(selectedIds.filter((x) => String(x) !== String(id)));
    else onChange([...selectedIds, id]);
  };

  const q = query.trim().toLowerCase();
  const visible = q
    ? admins.filter((a) =>
        `${a.first_name || ''} ${a.username || ''} ${a.user_id}`.toLowerCase().includes(q))
    : admins;

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.75 }}>
        <Typography variant="subtitle2" fontWeight={600}>{label}</Typography>
        <Chip size="small" variant="outlined" label={`${selectedIds.length} selected`} />
        {onRefresh && (
          <Tooltip title="Refresh admin list (keeps your selection)">
            <span>
              <IconButton size="small" onClick={onRefresh} disabled={loading} aria-label="Refresh admin list">
                {loading ? <CircularProgress size={16} /> : <Refresh fontSize="small" />}
              </IconButton>
            </span>
          </Tooltip>
        )}
      </Box>

      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mb: 1.25, minHeight: 28 }}>
        {selectedIds.length === 0 ? (
          <Typography variant="caption" color="text.secondary" sx={{ alignSelf: 'center' }}>
            None selected
          </Typography>
        ) : (
          selectedIds.map((id) => (
            <Chip
              key={String(id)}
              size="small"
              label={nameOf(id)}
              onDelete={() => onChange(selectedIds.filter((x) => String(x) !== String(id)))}
            />
          ))
        )}
      </Box>

      <Button size="small" variant="outlined" onClick={(e) => setAnchor(e.currentTarget)}>
        {buttonLabel}
      </Button>

      <Popover
        open={Boolean(anchor)}
        anchorEl={anchor}
        onClose={() => { setAnchor(null); setQuery(''); }}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
      >
        <Box sx={{ p: 1.5, width: { xs: 'min(320px, 90vw)', sm: 340 }, maxHeight: 400, overflowY: 'auto' }}>
          <TextField
            size="small" fullWidth autoFocus placeholder="Search admins"
            value={query} onChange={(e) => setQuery(e.target.value)}
            inputProps={{ 'aria-label': 'Search admins' }}
            InputProps={{ startAdornment: (<InputAdornment position="start"><Search fontSize="small" /></InputAdornment>) }}
            sx={{ mb: 1 }}
          />
          {loading ? (
            <CircularProgress size={20} />
          ) : admins.length === 0 ? (
            <Typography variant="caption" color="text.secondary">
              No admins loaded. Use refresh; your saved selection is kept.
            </Typography>
          ) : visible.length === 0 ? (
            <Typography variant="caption" color="text.secondary">No admins match.</Typography>
          ) : (
            <Stack spacing={0.5}>
              {visible.map((admin) => {
                const selected = selectedSet.has(String(admin.user_id));
                const blocked = requireDm && !admin.can_dm && !selected;
                return (
                  <Box
                    key={admin.user_id}
                    role="button"
                    tabIndex={blocked ? -1 : 0}
                    aria-pressed={selected}
                    aria-disabled={blocked}
                    onClick={() => { if (!blocked) toggle(admin); }}
                    onKeyDown={(e) => {
                      if (blocked) return;
                      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(admin); }
                    }}
                    sx={{
                      display: 'flex', alignItems: 'center', gap: 1, p: 0.75, borderRadius: 1,
                      cursor: blocked ? 'default' : 'pointer',
                      bgcolor: selected ? 'rgba(33,150,243,0.08)' : 'transparent',
                      opacity: blocked ? 0.65 : 1,
                      '&:hover': { bgcolor: blocked ? undefined : 'action.hover' },
                    }}
                  >
                    <Switch size="small" checked={selected} disabled={blocked} tabIndex={-1} onChange={() => {}} />
                    <Avatar sx={{ width: 24, height: 24, fontSize: '0.75rem' }}>
                      {(admin.first_name || '?')[0].toUpperCase()}
                    </Avatar>
                    <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                      <Typography variant="body2" fontWeight={500} noWrap sx={{ lineHeight: 1.2 }}>
                        {admin.first_name}{admin.username ? ` (@${admin.username})` : ''}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {admin.status === 'creator' ? 'Owner' : 'Admin'}
                      </Typography>
                    </Box>
                    {admin.can_dm ? (
                      <Chip label="✓ Started bot" color="success" size="small" variant="outlined" sx={{ fontSize: '0.68rem', height: 20 }} />
                    ) : (
                      <Chip label="Not started" color="warning" size="small" variant="outlined" sx={{ fontSize: '0.68rem', height: 20 }} />
                    )}
                  </Box>
                );
              })}
            </Stack>
          )}
        </Box>
      </Popover>

      {helperText && (
        <Typography variant="caption" color="text.secondary" display="block" mt={1}>
          {helperText}
        </Typography>
      )}
    </Box>
  );
}
