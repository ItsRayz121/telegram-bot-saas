import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert, Avatar, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, Drawer,
  IconButton, InputAdornment, ListItemIcon, ListItemText, Menu, MenuItem, Select, Skeleton, Stack, Table,
  TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, ToggleButton, ToggleButtonGroup,
  Tooltip, Typography,
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import {
  Close, ContentCopy, Delete, MoreVert, OpenInNew, PersonAdd, Refresh, Search, Send, VpnKey,
} from '@mui/icons-material';
import { toast } from 'react-toastify';
import { groupTeam } from '../services/api';
import {
  ALWAYS_OWNER_ONLY, FILTERS, ROLE_LABEL, ROLE_PERMISSIONS, STAGE_META, buildRows, canInvite, filterCounts,
  fmtDate, fmtDateTime, matchesFilter, matchesSearch, overview, relativeTime, stepsFor, timelineFor,
} from '../utils/teamAccess';

const errMsg = (e, fallback = 'Something went wrong.') => e?.response?.data?.error || fallback;

const toneColor = (theme, tone) => ({
  success: theme.palette.success.main,
  warning: theme.palette.warning.main,
  error: theme.palette.error.main,
  info: theme.palette.primary.main,
  neutral: theme.palette.text.secondary,
}[tone] || theme.palette.text.secondary);

function Badge({ tone = 'neutral', children, sx }) {
  return (
    <Box component="span" sx={(t) => ({
      display: 'inline-flex', alignItems: 'center', gap: 0.5, px: 1, py: 0.25, borderRadius: 1,
      fontSize: 12, fontWeight: 600, lineHeight: 1.5, whiteSpace: 'nowrap',
      color: toneColor(t, tone), bgcolor: alpha(toneColor(t, tone), 0.12),
      border: `1px solid ${alpha(toneColor(t, tone), 0.3)}`, ...sx,
    })}>
      {children}
    </Box>
  );
}

const STEP_COLOR = { done: 'success', warn: 'warning', error: 'error' };

function ProgressBar({ row, height = 4, width = 18 }) {
  const steps = stepsFor(row);
  const label = steps.map((s) => `${s.label}: ${{
    done: 'done', todo: 'not yet', warn: 'expired', error: 'failed', na: 'not applicable', unknown: 'unknown',
  }[s.state]}`).join(', ');
  return (
    <Tooltip title={label} arrow>
      <Box role="img" aria-label={`Progress. ${label}`} sx={{ display: 'inline-flex', gap: '3px' }}>
        {steps.map((s) => (
          <Box key={s.key} sx={(t) => ({
            width, height, borderRadius: 1,
            bgcolor: STEP_COLOR[s.state] ? toneColor(t, STEP_COLOR[s.state])
              : s.state === 'na' ? 'transparent' : alpha(t.palette.text.secondary, 0.22),
            border: s.state === 'na' ? `1px dashed ${t.palette.divider}` : 'none',
          })} />
        ))}
      </Box>
    </Tooltip>
  );
}

function Person({ row, size = 32 }) {
  const initials = (row.name || '?').split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase();
  return (
    <Stack direction="row" spacing={1.25} alignItems="center" sx={{ minWidth: 0 }}>
      <Avatar sx={(t) => ({
        width: size, height: size, fontSize: size * 0.4, fontWeight: 700,
        bgcolor: alpha(t.palette.primary.main, 0.18), color: t.palette.primary.light,
      })}>{initials}</Avatar>
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="body2" fontWeight={600} noWrap>{row.name}</Typography>
        <Typography variant="caption" color="text.secondary" noWrap display="block">
          {row.username ? `@${row.username}` : (row.email || (row.tgId ? `ID ${row.tgId}` : ''))}
        </Typography>
      </Box>
    </Stack>
  );
}

function StageBadge({ row }) {
  const m = STAGE_META[row.stage];
  return <Badge tone={m.tone}>{m.label}</Badge>;
}

function BotStatus({ row }) {
  if (row.botStarted === null || row.stage === 'inherited') {
    return <Typography variant="caption" color="text.disabled">{row.viaCode ? 'Not required' : '—'}</Typography>;
  }
  return (
    <Stack direction="row" spacing={0.75} alignItems="center">
      <Box sx={(t) => ({ width: 8, height: 8, borderRadius: '50%', bgcolor: row.botStarted ? t.palette.success.main : t.palette.text.disabled })} />
      <Typography variant="caption" color={row.botStarted ? 'text.primary' : 'text.secondary'}>
        {row.botStarted ? 'Started' : 'Not started'}
      </Typography>
    </Stack>
  );
}

function roleOf(row) {
  if (row.member) return row.member.role;
  if (row.stage === 'inherited') return row.inheritedRole;
  if (row.stage === 'pending') return row.latest?.role;
  return null;
}

function ExpiryCell({ row }) {
  const l = row.latest;
  if (!l || row.member) return <Typography variant="caption" color="text.disabled">—</Typography>;
  if (l.status === 'pending') {
    return (
      <Tooltip title={fmtDateTime(l.expires_at)}>
        <Typography variant="caption">{`Expires ${relativeTime(l.expires_at)}`}</Typography>
      </Tooltip>
    );
  }
  if (l.status === 'expired') {
    return <Typography variant="caption" color="text.secondary">{`Expired ${relativeTime(l.expires_at)}`}</Typography>;
  }
  return <Typography variant="caption" color="text.disabled">—</Typography>;
}

function Metric({ label, value, sub, loading }) {
  return (
    <Box sx={{ border: 1, borderColor: 'divider', borderRadius: 1.5, px: 2, py: 1.5, bgcolor: 'background.paper', minWidth: 0 }}>
      <Typography variant="caption" color="text.secondary" noWrap display="block">{label}</Typography>
      {loading ? <Skeleton width={56} height={36} /> : (
        <Typography variant="h5" fontWeight={700} sx={{ lineHeight: 1.3 }}>{value}</Typography>
      )}
      <Typography variant="caption" color="text.secondary" noWrap display="block" sx={{ minHeight: 18 }}>
        {loading ? ' ' : sub}
      </Typography>
    </Box>
  );
}

function copyText(text, label = 'Copied') {
  const fail = () => toast.info(`Copy this manually: ${text}`);
  try {
    if (!navigator.clipboard?.writeText) return fail();
    return navigator.clipboard.writeText(text).then(() => toast.success(label), fail);
  } catch { return fail(); }
}

function RoleHelp({ role }) {
  return (
    <Box component="ul" sx={{ m: 0, pl: 2.25, color: 'text.secondary', fontSize: 13, '& li': { mb: 0.25 } }}>
      {(ROLE_PERMISSIONS[role] || []).map((p) => <li key={p}>{p}</li>)}
    </Box>
  );
}

function ConfirmDialog({ confirm, busy, onClose, onConfirm }) {
  return (
    <Dialog open={!!confirm} onClose={busy ? undefined : onClose} maxWidth="xs" fullWidth aria-labelledby="ta-confirm-title">
      <DialogTitle id="ta-confirm-title">{confirm?.title}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" component="div">{confirm?.body}</Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant="contained" color={confirm?.danger ? 'error' : 'primary'} disabled={busy} onClick={onConfirm} autoFocus
          sx={confirm?.danger ? (t) => ({
            background: t.palette.error.main, boxShadow: 'none',
            '&:hover': { background: t.palette.error.dark, boxShadow: 'none' },
          }) : undefined}>
          {confirm?.confirmLabel || 'Confirm'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function InviteDialog({ open, candidates, initialKey, disabledReason, onClose, onSend, onOpenCodes }) {
  const [key, setKey] = useState('');
  const [role, setRole] = useState('manager');
  const [sending, setSending] = useState(false);
  useEffect(() => { if (open) { setKey(initialKey || ''); setRole('manager'); } }, [open, initialKey]);
  const chosen = candidates.find((c) => c.key === key);
  const send = async () => {
    if (!chosen || sending) return;
    setSending(true);
    await onSend(chosen, role);
    setSending(false);
    onClose();
  };
  return (
    <Dialog open={open} onClose={sending ? undefined : onClose} maxWidth="xs" fullWidth aria-labelledby="ta-invite-title">
      <DialogTitle id="ta-invite-title">Invite a team member</DialogTitle>
      <DialogContent>
        {disabledReason ? (
          <Alert severity="info" sx={{ mb: 1 }}>{disabledReason}</Alert>
        ) : candidates.length === 0 ? (
          <Alert severity="info" sx={{ mb: 1 }}>
            No administrator is ready to be invited. Admins must open the bot and press Start first (the bot never
            messages anyone who has not). You can share an access code instead.
          </Alert>
        ) : (
          <Stack spacing={2} sx={{ mt: 0.5 }}>
            <Box>
              <Typography variant="caption" color="text.secondary" component="label" htmlFor="ta-invite-person">Telegram administrator</Typography>
              <Select fullWidth size="small" displayEmpty id="ta-invite-person" value={key}
                onChange={(e) => setKey(e.target.value)} inputProps={{ 'aria-label': 'Telegram administrator' }}>
                <MenuItem value="" disabled>Choose an administrator</MenuItem>
                {candidates.map((c) => (
                  <MenuItem key={c.key} value={c.key}>{c.name}{c.username ? `  @${c.username}` : ''}</MenuItem>
                ))}
              </Select>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>Role</Typography>
              <ToggleButtonGroup size="small" color="primary" exclusive fullWidth value={role}
                onChange={(_, v) => v && setRole(v)} aria-label="Role">
                <ToggleButton value="manager" sx={{ textTransform: 'none' }}>Manager</ToggleButton>
                <ToggleButton value="viewer" sx={{ textTransform: 'none' }}>Viewer</ToggleButton>
              </ToggleButtonGroup>
              <Box sx={{ mt: 1 }}><RoleHelp role={role} /></Box>
            </Box>
            <Typography variant="caption" color="text.secondary">
              They get a Telegram message with Accept / Reject buttons. Nothing changes until they accept. Invitations expire after 7 days.
            </Typography>
          </Stack>
        )}
      </DialogContent>
      <DialogActions sx={{ justifyContent: 'space-between', px: 3, pb: 2 }}>
        <Button size="small" startIcon={<VpnKey />} onClick={onOpenCodes} disabled={sending}>Use an access code</Button>
        <Stack direction="row" spacing={1}>
          <Button onClick={onClose} disabled={sending}>Cancel</Button>
          <Button variant="contained" startIcon={<Send />} disabled={!chosen || sending || !!disabledReason} onClick={send}>
            {sending ? 'Sending…' : 'Send invitation'}
          </Button>
        </Stack>
      </DialogActions>
    </Dialog>
  );
}

function CodesDialog({ open, codes, max, slotsFull, disabled, onClose, onCreate, onRevoke }) {
  const [role, setRole] = useState('manager');
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth aria-labelledby="ta-codes-title">
      <DialogTitle id="ta-codes-title">Access codes</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          Share a one-time code with someone who is not an admin of the Telegram group, or who has not started the bot.
          They paste it under “Join with access code”. Each code works once and expires after 7 days; it counts toward the
          {` ${max}`}-member limit until it is used or revoked.
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
          <ToggleButtonGroup size="small" color="primary" exclusive value={role} onChange={(_, v) => v && setRole(v)}
            aria-label="Role for the new access code">
            <ToggleButton value="manager" sx={{ textTransform: 'none' }}>Manager</ToggleButton>
            <ToggleButton value="viewer" sx={{ textTransform: 'none' }}>Viewer</ToggleButton>
          </ToggleButtonGroup>
          <Button variant="contained" size="small" startIcon={<VpnKey />} disabled={disabled || slotsFull} onClick={() => onCreate(role)}>
            Create code
          </Button>
          {slotsFull && <Typography variant="caption" color="warning.main">Member limit reached</Typography>}
        </Stack>
        <Divider sx={{ mb: 1 }} />
        {codes.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>No open access codes.</Typography>
        ) : (
          <Stack divider={<Divider flexItem />}>
            {codes.map((c) => (
              <Stack key={c.id} direction="row" alignItems="center" spacing={1} sx={{ py: 1 }}>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Typography sx={{ fontFamily: 'monospace', fontSize: 13, wordBreak: 'break-all' }}>{c.code}</Typography>
                    <Badge tone={c.role === 'manager' ? 'info' : 'neutral'}>{ROLE_LABEL[c.role] || c.role}</Badge>
                  </Stack>
                  <Typography variant="caption" color="text.secondary">
                    {`Expires ${fmtDate(c.expires_at)} (${relativeTime(c.expires_at)})`}
                  </Typography>
                </Box>
                <Tooltip title="Copy code">
                  <IconButton size="small" aria-label={`Copy access code ending ${String(c.code).slice(-4)}`} onClick={() => copyText(c.code, 'Code copied')}>
                    <ContentCopy fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Revoke code">
                  <span>
                    <IconButton size="small" disabled={disabled} aria-label={`Revoke access code ending ${String(c.code).slice(-4)}`} onClick={() => onRevoke(c)}>
                      <Delete fontSize="small" />
                    </IconButton>
                  </span>
                </Tooltip>
              </Stack>
            ))}
          </Stack>
        )}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Close</Button></DialogActions>
    </Dialog>
  );
}

function Section({ title, children }) {
  return (
    <Box sx={{ py: 2 }}>
      <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: '0.08em', display: 'block', mb: 0.75 }}>{title}</Typography>
      {children}
    </Box>
  );
}

function Field({ label, children }) {
  return (
    <Stack direction="row" justifyContent="space-between" spacing={2} sx={{ py: 0.5 }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography variant="body2" component="div" sx={{ textAlign: 'right', minWidth: 0, wordBreak: 'break-word' }}>{children}</Typography>
    </Stack>
  );
}

function DetailDrawer({
  row, onClose, bot, acting, directBlocked, resendBlocked, inviteRole, setInviteRole, now,
  onInvite, onResend, onCancel, onRevoke, onRoleChange,
}) {
  const open = !!row;
  const steps = row ? stepsFor(row) : [];
  const timeline = row ? timelineFor(row) : [];
  const botLink = bot?.username ? `https://t.me/${bot.username}` : null;
  const busy = !!acting;
  const pending = row?.stage === 'pending' ? row.latest : null;
  const stepIcon = { done: 'success', warn: 'warning', error: 'error' };
  return (
    <Drawer anchor="right" open={open} onClose={onClose}
      PaperProps={{ sx: { width: { xs: '100%', sm: 440 }, bgcolor: 'background.paper', backgroundImage: 'none' }, 'aria-labelledby': 'ta-drawer-title' }}>
      {row && (
        <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
            <Box sx={{ flex: 1, minWidth: 0 }}><Person row={row} size={40} /></Box>
            <StageBadge row={row} />
            <IconButton onClick={onClose} aria-label="Close details" edge="end"><Close /></IconButton>
          </Stack>
          <Box sx={{ flex: 1, overflowY: 'auto', px: 2.5 }}>
            <Typography id="ta-drawer-title" sx={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}>
              {`${row.name} — team access details`}
            </Typography>

            <Section title="Telegram profile">
              <Field label="Name">{row.name}</Field>
              <Field label="Username">
                {row.username ? (
                  <Box component="a" href={`https://t.me/${row.username}`} target="_blank" rel="noopener noreferrer"
                    sx={{ color: 'primary.light', textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}>
                    @{row.username} <OpenInNew sx={{ fontSize: 12, verticalAlign: 'middle' }} />
                  </Box>
                ) : 'No public username'}
              </Field>
              {row.tgId && <Field label="Telegram ID"><span style={{ fontFamily: 'monospace' }}>{row.tgId}</span></Field>}
              {row.tgStatus && <Field label="In the Telegram group">{row.tgStatus === 'creator' ? 'Creator' : 'Administrator'}</Field>}
              {row.isAdmin === false && <Field label="In the Telegram group">No longer an administrator</Field>}
              {row.member && <Field label="Telegizer account">{row.member.full_name || row.member.email}{row.member.full_name && row.member.email ? ` · ${row.member.email}` : ''}</Field>}
              {row.stage === 'inherited' && <Field label="Access comes from">{row.inheritedFrom === '__official__' ? 'the official bot (whole bot)' : `@${row.inheritedFrom} (whole bot)`}</Field>}
            </Section>
            <Divider />

            {row.stage !== 'inherited' && !row.viaCode && (
              <>
                <Section title="Bot readiness">
                  <Stack direction="row" alignItems="center" spacing={1}><BotStatus row={row} /></Stack>
                  {row.botStarted === false && (
                    <>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                        {`They need to open ${bot?.username ? `@${bot.username}` : 'the bot'} in Telegram and press Start. Until then the bot cannot message them, so no invitation can be sent.`}
                      </Typography>
                      {botLink && (
                        <Button size="small" sx={{ mt: 1 }} startIcon={<ContentCopy />} onClick={() => copyText(botLink, 'Bot link copied')}>
                          Copy bot link
                        </Button>
                      )}
                    </>
                  )}
                  {row.botStarted === null && (
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                      Bot status can’t be checked right now (the Telegram admin list is unavailable or they are no longer an administrator).
                    </Typography>
                  )}
                </Section>
                <Divider />
              </>
            )}

            <Section title="Invitation progress">
              <Stack spacing={1} component="ol" sx={{ listStyle: 'none', p: 0, m: 0 }}>
                {steps.map((s) => (
                  <Stack key={s.key} component="li" direction="row" spacing={1.25} alignItems="center">
                    <Box sx={(t) => ({
                      width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
                      bgcolor: stepIcon[s.state] ? toneColor(t, stepIcon[s.state]) : 'transparent',
                      border: stepIcon[s.state] ? 'none' : `1.5px ${s.state === 'na' ? 'dashed' : 'solid'} ${t.palette.text.disabled}`,
                    })} />
                    <Typography variant="body2" color={s.state === 'todo' || s.state === 'na' || s.state === 'unknown' ? 'text.secondary' : 'text.primary'}>
                      {s.label}
                      {s.state === 'na' && ' — not applicable'}
                      {s.state === 'unknown' && ' — unknown'}
                    </Typography>
                  </Stack>
                ))}
              </Stack>
              {row.stage === 'revoked' && (
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                  They accepted the invitation, but their access has since been removed. The time of removal isn’t recorded here.
                </Typography>
              )}
              {pending && (
                <Typography variant="body2" sx={{ mt: 1.5 }}>
                  {`Waiting for them to accept. Expires ${fmtDateTime(pending.expires_at)} (${relativeTime(pending.expires_at, now)}).`}
                </Typography>
              )}
            </Section>
            <Divider />

            <Section title="History">
              {timeline.length === 0 ? (
                <Typography variant="body2" color="text.secondary">No invitations recorded in the last 90 days.</Typography>
              ) : (
                <Stack spacing={1.25}>
                  {timeline.map((e, i) => (
                    <Stack key={`${e.at}-${i}`} direction="row" spacing={1.25} alignItems="baseline">
                      <Box sx={(t) => ({ width: 8, height: 8, borderRadius: '50%', bgcolor: toneColor(t, e.tone), flexShrink: 0, mt: '5px' })} />
                      <Box>
                        <Typography variant="body2">{e.text}</Typography>
                        <Typography variant="caption" color="text.secondary">{fmtDateTime(e.at)}</Typography>
                      </Box>
                    </Stack>
                  ))}
                </Stack>
              )}
              <Typography variant="caption" color="text.disabled" display="block" sx={{ mt: 1.5 }}>
                Cancelled invitations are deleted and don’t appear here.
              </Typography>
            </Section>
            <Divider />

            <Section title="Role & permissions">
              {row.member ? (
                <>
                  <Select size="small" fullWidth value={row.member.role} disabled={busy}
                    inputProps={{ 'aria-label': `Role for ${row.name}` }}
                    onChange={(e) => e.target.value !== row.member.role && onRoleChange(row, e.target.value)}>
                    <MenuItem value="manager">Manager</MenuItem>
                    <MenuItem value="viewer">Viewer</MenuItem>
                  </Select>
                  <Box sx={{ mt: 1 }}><RoleHelp role={row.member.role} /></Box>
                </>
              ) : row.stage === 'inherited' ? (
                <>
                  <Badge tone="info">{ROLE_LABEL[row.inheritedRole] || row.inheritedRole}</Badge>
                  <Box sx={{ mt: 1 }}><RoleHelp role={row.inheritedRole} /></Box>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                    Change or remove this in “Share a whole bot” on My Groups.
                  </Typography>
                </>
              ) : pending ? (
                <>
                  <Badge tone="info">{ROLE_LABEL[pending.role] || pending.role}</Badge>
                  <Box sx={{ mt: 1 }}><RoleHelp role={pending.role} /></Box>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                    To use a different role, cancel this invitation and send a new one.
                  </Typography>
                </>
              ) : canInvite(row) ? (
                <>
                  <ToggleButtonGroup size="small" color="primary" exclusive fullWidth value={inviteRole}
                    onChange={(_, v) => v && setInviteRole(v)} aria-label="Role for the invitation">
                    <ToggleButton value="manager" sx={{ textTransform: 'none' }}>Manager</ToggleButton>
                    <ToggleButton value="viewer" sx={{ textTransform: 'none' }}>Viewer</ToggleButton>
                  </ToggleButtonGroup>
                  <Box sx={{ mt: 1 }}><RoleHelp role={inviteRole} /></Box>
                </>
              ) : (
                <Typography variant="body2" color="text.secondary">No role yet. Roles are chosen when you invite someone.</Typography>
              )}
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1.5 }}>
                Never available to team members:
              </Typography>
              <Box component="ul" sx={{ m: 0, pl: 2.25, color: 'text.secondary', fontSize: 12.5 }}>
                {ALWAYS_OWNER_ONLY.map((p) => <li key={p}>{p}</li>)}
              </Box>
            </Section>
          </Box>

          <Stack direction="row" spacing={1} sx={{ p: 2, borderTop: 1, borderColor: 'divider' }} justifyContent="flex-end" flexWrap="wrap" useFlexGap>
            {row.stage === 'pending' && (
              <>
                <Button color="error" disabled={busy} startIcon={<Close />} onClick={() => onCancel(row)}>Cancel invitation</Button>
                <Button variant="contained" disabled={busy || resendBlocked} startIcon={<Send />} onClick={() => onResend(row)}>Resend</Button>
              </>
            )}
            {row.stage === 'active' && (
              <Button color="error" variant="outlined" disabled={busy} startIcon={<Delete />} onClick={() => onRevoke(row)}>Revoke access</Button>
            )}
            {canInvite(row) && (
              <Tooltip title={directBlocked || ''}>
                <span>
                  <Button variant="contained" disabled={busy || !!directBlocked} startIcon={<PersonAdd />} onClick={() => onInvite(row, inviteRole)}>
                    {row.history.length ? 'Send a new invitation' : 'Send invitation'}
                  </Button>
                </span>
              </Tooltip>
            )}
            <Button onClick={onClose}>Close</Button>
          </Stack>
        </Box>
      )}
    </Drawer>
  );
}

export default function TeamAccessDashboard({ group }) {
  const gid = group?.telegram_group_id;
  const [team, setTeam] = useState(null);
  const [teamErr, setTeamErr] = useState('');
  const [admins, setAdmins] = useState(null);
  const [adminsErr, setAdminsErr] = useState('');
  const [bot, setBot] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [selectedKey, setSelectedKey] = useState(null);
  const [inviteRole, setInviteRole] = useState('manager');
  const [inviteDialog, setInviteDialog] = useState({ open: false, key: '' });
  const [codesOpen, setCodesOpen] = useState(false);
  const [menu, setMenu] = useState(null); // { anchor, row }
  const [confirm, setConfirm] = useState(null);
  const [acting, setActing] = useState(null);
  const [now, setNow] = useState(Date.now());
  const actingRef = useRef(null);
  const mounted = useRef(true);
  const lastLoad = useRef(0);
  const teamRef = useRef(null);

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  const load = useCallback(async ({ silent = false } = {}) => {
    if (!gid) return;
    if (!silent) setRefreshing(true);
    const [t, a] = await Promise.allSettled([groupTeam.get(gid), groupTeam.admins(gid)]);
    if (!mounted.current) return;
    lastLoad.current = Date.now();
    if (t.status === 'fulfilled') {
      teamRef.current = t.value.data;
      setTeam(t.value.data);
      setTeamErr('');
    } else if (!silent || !teamRef.current) {
      setTeamErr(errMsg(t.reason, 'Could not load team access.'));
    }
    if (a.status === 'fulfilled') {
      const d = a.value.data || {};
      setBot({ username: d.bot_username || '', official: !!d.bot_official });
      if (d.error || d.supported === false) { setAdmins(null); setAdminsErr(d.error || 'The Telegram admin list is unavailable.'); }
      else { setAdmins(d.admins || []); setAdminsErr(''); }
    } else if (!silent) {
      setAdmins(null);
      setAdminsErr(errMsg(a.reason, 'Could not load the group admins from Telegram.'));
    }
    setNow(Date.now());
    setLoading(false);
    setRefreshing(false);
  }, [gid]);

  useEffect(() => { setLoading(true); setTeam(null); teamRef.current = null; setAdmins(null); load(); }, [gid, load]);

  // Acceptance happens in Telegram, so re-check on a timer while something is pending and when the tab regains focus.
  const hasPending = !!team?.invitations?.some((i) => i.status === 'pending');
  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === 'visible' && !actingRef.current) load({ silent: true });
    };
    const onFocus = () => { if (Date.now() - lastLoad.current > 10000) tick(); };
    const timer = hasPending ? setInterval(tick, 30000) : null;
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onFocus);
    return () => {
      if (timer) clearInterval(timer);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onFocus);
    };
  }, [hasPending, load]);

  // One action at a time; always re-read the server afterwards (it is the source of truth).
  const act = useCallback(async (key, fn, okMsg) => {
    if (actingRef.current) return false;
    actingRef.current = key;
    setActing(key);
    let ok = false;
    try {
      await fn();
      ok = true;
      if (okMsg) toast.success(okMsg);
    } catch (e) {
      toast.error(errMsg(e));
    }
    await load({ silent: true });
    actingRef.current = null;
    if (mounted.current) setActing(null);
    return ok;
  }, [load]);

  const rows = useMemo(() => (team ? buildRows({
    admins, members: team.members || [], invitations: team.invitations || [], inherited: team.inherited || [],
  }) : []), [team, admins]);
  const counts = useMemo(() => filterCounts(rows), [rows]);
  const visible = useMemo(() => rows.filter((r) => matchesFilter(r, filter) && matchesSearch(r, search)), [rows, filter, search]);
  const stats = useMemo(() => (team ? overview({
    admins, members: team.members || [], invitations: team.invitations || [], codes: team.invites || [], max: team.max_members,
  }) : null), [team, admins]);
  const selected = rows.find((r) => r.key === selectedKey) || null;
  useEffect(() => { if (selectedKey && team && !rows.some((r) => r.key === selectedKey)) setSelectedKey(null); }, [rows, selectedKey, team]);

  const max = team?.max_members || 10;
  const slotsFull = !!stats && stats.active + stats.reserved >= max;
  let directBlocked = '';
  if (team && !team.direct_enabled) directBlocked = 'Direct Telegram invitations are unavailable for this group right now. Use an access code instead.';
  else if (adminsErr && admins === null) directBlocked = 'The Telegram admin list could not be loaded, so invitations are paused. Try refreshing.';
  else if (slotsFull) directBlocked = `The limit of ${max} team members (including pending invitations and open codes) is reached.`;

  const sendInvite = (row, role) => act(`invite-${row.key}`, () => groupTeam.inviteAdmin(gid, row.tgId, role),
    `Invitation sent to ${row.name}. Access starts only when they accept.`);

  const askInvite = (row, role) => setConfirm({
    title: `Invite ${row.name}?`,
    body: (
      <>
        <p style={{ marginTop: 0 }}>{`${row.name} will get a Telegram message with Accept / Reject buttons, as a ${ROLE_LABEL[role]}.`}</p>
        <RoleHelp role={role} />
      </>
    ),
    confirmLabel: 'Send invitation',
    run: () => sendInvite(row, role),
  });

  const askResend = (row) => act(`resend-${row.key}`, () => groupTeam.resendInvite(gid, row.latest.id),
    `Invitation sent again to ${row.name}.`);

  const askCancel = (row) => setConfirm({
    title: 'Cancel this invitation?',
    body: `${row.name} will no longer be able to accept it. The invitation is deleted; you can send a new one later.`,
    confirmLabel: 'Cancel invitation', danger: true,
    run: () => act(`cancel-${row.key}`, () => groupTeam.cancelInvite(gid, row.latest.id), 'Invitation cancelled'),
  });

  const askRevoke = (row) => setConfirm({
    title: `Revoke ${row.name}’s access?`,
    body: 'They lose access to this group immediately. Anything they changed stays as it is. You can invite them again later.',
    confirmLabel: 'Revoke access', danger: true,
    run: () => act(`revoke-${row.key}`, () => groupTeam.removeMember(gid, row.member.user_id), 'Access revoked'),
  });

  const askRole = (row, role) => setConfirm({
    title: `Change ${row.name}’s role?`,
    body: (
      <>
        <p style={{ marginTop: 0 }}>{`From ${ROLE_LABEL[row.member.role]} to ${ROLE_LABEL[role]}. This takes effect immediately.`}</p>
        <RoleHelp role={role} />
      </>
    ),
    confirmLabel: `Make ${ROLE_LABEL[role]}`,
    run: () => act(`role-${row.key}`, () => groupTeam.setRole(gid, row.member.user_id, role), `${row.name} is now a ${ROLE_LABEL[role]}`),
  });

  const askRevokeCode = (c) => setConfirm({
    title: 'Revoke this access code?',
    body: 'Nobody will be able to use it any more. If someone already used it, nothing changes for them.',
    confirmLabel: 'Revoke code', danger: true,
    run: () => act(`code-${c.id}`, () => groupTeam.cancelInvite(gid, c.id), 'Code revoked'),
  });

  const runConfirm = async () => {
    const c = confirm;
    if (!c) return;
    setConfirm((cur) => cur && { ...cur, working: true });
    await c.run();
    if (mounted.current) setConfirm(null);
  };

  const openInvite = (key = '') => setInviteDialog({ open: true, key });
  const candidates = rows.filter(canInvite);
  const emptyAll = team && rows.length === 0;

  // ── Row action ──
  const primaryAction = (row) => {
    const locked = !!acting;
    if (row.stage === 'pending') {
      return <Button size="small" variant="outlined" disabled={locked || !team.direct_enabled}
        onClick={() => askResend(row)}>Resend</Button>;
    }
    if (canInvite(row)) {
      const label = row.history.length ? 'Invite again' : 'Invite';
      return (
        <Tooltip title={directBlocked}>
          <span>
            <Button size="small" variant="contained" disabled={locked || !!directBlocked} startIcon={<PersonAdd />}
              onClick={() => openInvite(row.key)}>{label}</Button>
          </span>
        </Tooltip>
      );
    }
    if (row.stage === 'active') return <Button size="small" onClick={() => setSelectedKey(row.key)}>Edit access</Button>;
    return <Button size="small" onClick={() => setSelectedKey(row.key)}>Details</Button>;
  };
  const hasMenu = (row) => row.stage === 'pending' || row.stage === 'active';

  if (loading) {
    return (
      <Box aria-busy="true" aria-label="Loading team access">
        <Skeleton width={180} height={36} />
        <Skeleton width={320} height={20} sx={{ mb: 2 }} />
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2,1fr)', md: 'repeat(4,1fr)' }, gap: 1.5, mb: 2 }}>
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} variant="rounded" height={84} />)}
        </Box>
        {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} height={52} />)}
      </Box>
    );
  }

  if (!team) {
    return (
      <Alert severity="error" action={<Button color="inherit" size="small" onClick={() => { setLoading(true); load(); }}>Retry</Button>}>
        {teamErr || 'Could not load team access.'}
      </Alert>
    );
  }

  return (
    <Box>
      {/* Header */}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} justifyContent="space-between" alignItems={{ sm: 'center' }} sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h5" component="h2" fontWeight={700}>Team Access</Typography>
          <Typography variant="body2" color="text.secondary">
            Invite this group’s Telegram admins, manage roles and see who can open it in Telegizer.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Tooltip title="Refresh">
            <span>
              <IconButton onClick={() => load()} disabled={refreshing || !!acting} aria-label="Refresh team access">
                <Refresh sx={refreshing ? { animation: 'ta-spin 1s linear infinite', '@keyframes ta-spin': { to: { transform: 'rotate(360deg)' } } } : undefined} />
              </IconButton>
            </span>
          </Tooltip>
          <Button variant="outlined" startIcon={<VpnKey />} onClick={() => setCodesOpen(true)}>
            {`Access codes${stats.codes ? ` (${stats.codes})` : ''}`}
          </Button>
          <Button variant="contained" startIcon={<PersonAdd />} disabled={!!acting} onClick={() => openInvite()}>Invite member</Button>
        </Stack>
      </Stack>

      {teamErr && <Alert severity="warning" sx={{ mb: 1.5 }} onClose={() => setTeamErr('')}>{teamErr}</Alert>}
      {adminsErr && (
        <Alert severity="warning" sx={{ mb: 1.5 }}
          action={<Button color="inherit" size="small" onClick={() => load()}>Retry</Button>}>
          {`Couldn’t read this group’s admins from Telegram (${String(adminsErr).replace(/\.$/, '')}). People who already have access or an invitation are still listed.`}
        </Alert>
      )}
      {!adminsErr && !team.direct_enabled && (
        <Alert severity="info" sx={{ mb: 1.5 }} action={<Button color="inherit" size="small" onClick={() => setCodesOpen(true)}>Access codes</Button>}>
          Direct Telegram invitations aren’t available for this group right now. You can still share an access code.
        </Alert>
      )}

      {/* Overview */}
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2,minmax(0,1fr))', md: 'repeat(4,minmax(0,1fr))' }, gap: 1.5, mb: 2.5 }}>
        <Metric label="Active members" value={`${stats.active} / ${stats.max}`}
          sub={stats.reserved ? `${stats.reserved} more reserved by invites/codes` : `${stats.max - stats.active} slots free`} />
        <Metric label="Pending invitations" value={stats.pending} sub={stats.pending ? 'Waiting to accept' : 'None waiting'} />
        <Metric label="Bot-ready admins" value={stats.botReady ?? '—'}
          sub={stats.adminCount != null ? `of ${stats.adminCount} administrators` : 'Admin list unavailable'} />
        <Metric label="Haven’t started the bot" value={stats.notStarted ?? '—'}
          sub={stats.notStarted ? 'Can’t be invited yet' : stats.notStarted === 0 ? 'Everyone is ready' : 'Admin list unavailable'} />
      </Box>

      {/* Toolbar */}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} justifyContent="space-between" alignItems={{ md: 'center' }} sx={{ mb: 1.5 }}>
        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap role="group" aria-label="Filter administrators">
          {FILTERS.map((f) => {
            const active = filter === f.id;
            return (
              <Chip key={f.id} clickable onClick={() => setFilter(f.id)} aria-pressed={active}
                color={active ? 'primary' : 'default'} variant={active ? 'filled' : 'outlined'}
                label={`${f.label} · ${counts[f.id]}`} sx={{ fontWeight: 600 }} />
            );
          })}
        </Stack>
        <TextField size="small" placeholder="Search name, username or ID" value={search}
          onChange={(e) => setSearch(e.target.value)} sx={{ minWidth: { md: 280 } }}
          inputProps={{ 'aria-label': 'Search administrators' }}
          InputProps={{
            startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment>,
            endAdornment: search ? (
              <InputAdornment position="end">
                <IconButton size="small" aria-label="Clear search" onClick={() => setSearch('')}><Close fontSize="small" /></IconButton>
              </InputAdornment>
            ) : null,
          }} />
      </Stack>

      {/* Unified table */}
      <TableContainer sx={{ border: 1, borderColor: 'divider', borderRadius: 1.5, bgcolor: 'background.paper' }}>
        <Table size="small" aria-label="Group administrators and team access">
          <TableHead>
            <TableRow sx={{ '& th': { color: 'text.secondary', fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap', borderColor: 'divider' } }}>
              <TableCell>Administrator</TableCell>
              <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' } }}>Bot</TableCell>
              <TableCell>Invitation</TableCell>
              <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' } }}>Role</TableCell>
              <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>Expires</TableCell>
              <TableCell align="right"><span style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}>Actions</span></TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {visible.map((row) => {
              const role = roleOf(row);
              return (
                <TableRow key={row.key} hover tabIndex={0} selected={selectedKey === row.key}
                  onClick={() => setSelectedKey(row.key)}
                  onKeyDown={(e) => {
                    if (e.target !== e.currentTarget) return;
                    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedKey(row.key); }
                  }}
                  aria-label={`${row.name}, ${STAGE_META[row.stage].label}. Open details`}
                  sx={{ cursor: 'pointer', '& td': { borderColor: 'divider', py: 1.1 }, '&:last-child td': { border: 0 }, '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main', outlineOffset: -2 } }}>
                  <TableCell sx={{ maxWidth: { xs: 170, sm: 260 } }}><Person row={row} /></TableCell>
                  <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' } }}><BotStatus row={row} /></TableCell>
                  <TableCell>
                    <Stack spacing={0.75} alignItems="flex-start">
                      <StageBadge row={row} />
                      {row.stage !== 'inherited' && <ProgressBar row={row} />}
                    </Stack>
                  </TableCell>
                  <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' } }}>
                    {role ? <Badge tone={role === 'manager' ? 'info' : 'neutral'}>{ROLE_LABEL[role] || role}</Badge>
                      : <Typography variant="caption" color="text.disabled">—</Typography>}
                  </TableCell>
                  <TableCell sx={{ display: { xs: 'none', md: 'table-cell' }, whiteSpace: 'nowrap' }}><ExpiryCell row={row} /></TableCell>
                  <TableCell align="right" onClick={(e) => e.stopPropagation()} sx={{ whiteSpace: 'nowrap' }}>
                    {primaryAction(row)}
                    {hasMenu(row) && (
                      <IconButton size="small" aria-label={`More actions for ${row.name}`} aria-haspopup="menu" disabled={!!acting}
                        onClick={(e) => setMenu({ anchor: e.currentTarget, row })}>
                        <MoreVert fontSize="small" />
                      </IconButton>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        {visible.length === 0 && (
          <Box sx={{ textAlign: 'center', py: 5, px: 2 }}>
            {emptyAll ? (
              <>
                <Typography fontWeight={600}>
                  {adminsErr ? 'No one to show yet' : 'No other administrators found'}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 2 }}>
                  {adminsErr
                    ? 'Telegram’s admin list is unavailable right now. You can still share an access code.'
                    : 'Make someone an administrator of the Telegram group, then refresh. Or share an access code with them.'}
                </Typography>
                <Button variant="outlined" startIcon={<VpnKey />} onClick={() => setCodesOpen(true)}>Create an access code</Button>
              </>
            ) : (
              <>
                <Typography fontWeight={600}>Nothing matches</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 1.5 }}>Try a different filter or search.</Typography>
                <Button size="small" onClick={() => { setFilter('all'); setSearch(''); }}>Clear filters</Button>
              </>
            )}
          </Box>
        )}
      </TableContainer>
      <Typography variant="caption" color="text.disabled" display="block" sx={{ mt: 1 }} aria-live="polite">
        {`Showing ${visible.length} of ${rows.length}. Pending invitations refresh automatically.`}
      </Typography>

      {/* Row menu */}
      <Menu open={!!menu} anchorEl={menu?.anchor} onClose={() => setMenu(null)}>
        {menu?.row.stage === 'pending' && (
          <MenuItem onClick={() => { const r = menu.row; setMenu(null); askCancel(r); }}>
            <ListItemIcon><Close fontSize="small" /></ListItemIcon><ListItemText>Cancel invitation</ListItemText>
          </MenuItem>
        )}
        {menu?.row.stage === 'active' && (
          <MenuItem onClick={() => { const r = menu.row; setMenu(null); askRevoke(r); }} sx={{ color: 'error.main' }}>
            <ListItemIcon><Delete fontSize="small" color="error" /></ListItemIcon><ListItemText>Revoke access</ListItemText>
          </MenuItem>
        )}
      </Menu>

      <DetailDrawer row={selected} onClose={() => setSelectedKey(null)} bot={bot} acting={acting} now={now}
        directBlocked={directBlocked} resendBlocked={!team.direct_enabled} inviteRole={inviteRole} setInviteRole={setInviteRole}
        onInvite={askInvite} onResend={askResend} onCancel={askCancel} onRevoke={askRevoke} onRoleChange={askRole} />

      <InviteDialog open={inviteDialog.open} candidates={candidates} initialKey={inviteDialog.key}
        disabledReason={directBlocked}
        onClose={() => setInviteDialog((d) => ({ ...d, open: false }))}
        onSend={sendInvite}
        onOpenCodes={() => { setInviteDialog((d) => ({ ...d, open: false })); setCodesOpen(true); }} />

      <CodesDialog open={codesOpen} codes={team.invites || []} max={max} slotsFull={slotsFull} disabled={!!acting}
        onClose={() => setCodesOpen(false)}
        onCreate={(role) => act('code-new', () => groupTeam.createInvite(gid, role), 'Access code created')}
        onRevoke={askRevokeCode} />

      <ConfirmDialog confirm={confirm} busy={!!confirm?.working} onClose={() => setConfirm(null)} onConfirm={runConfirm} />
    </Box>
  );
}
