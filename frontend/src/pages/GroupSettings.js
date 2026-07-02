import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, AppBar, Toolbar, Typography, IconButton, Tabs, Tab,
  Card, CardContent, Button, TextField, Switch, FormControlLabel,
  Grid, CircularProgress, Chip, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, Select, MenuItem,
  FormControl, InputLabel, Pagination, Divider, Dialog, DialogTitle,
  DialogContent, DialogActions, Tooltip, Alert, Stack, Avatar, Popover,
  Menu, InputAdornment, ListItemIcon, ListItemText,
  useTheme, useMediaQuery,
} from '@mui/material';
import {
  ArrowBack, Save, Add, Delete, CheckCircle, Schedule,
  Send, Assessment, People, SmartToy, Refresh,
  Warning as WarningIcon, EmojiEvents, FileDownload,
  Search, Block, Gavel, VolumeOff, VolumeUp, LockOpen, PersonRemove,
  Campaign,
} from '@mui/icons-material';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import { settings, digest as digestApi } from '../services/api';
import { track } from '../services/analytics';
import RaidCreator from '../components/RaidCreator';
import ScheduledMessages from '../components/ScheduledMessages';
import KnowledgeBase from '../components/KnowledgeBase';
import PollCreator from '../components/PollCreator';
import WebhookManager from '../components/WebhookManager';
import WorkspaceForwarding from './WorkspaceForwarding';
import WorkspaceAutomations from './WorkspaceAutomations';
import InviteLinks from '../components/InviteLinks';
import CampaignManager from '../components/CampaignManager';
import ForumTopicSelector from '../components/ForumTopicSelector';
import TimezoneSelect from '../components/TimezoneSelect';
import {
  buildCategories,
  getSubTabIndex,
  PRO_GATED_SECTIONS,
  PRO_GATED_LABELS,
} from '../config/featureRegistry';
import PlanGate from '../components/PlanGate';
import { UiPrefsProvider, useUiPrefs } from '../context/UiPrefsContext';
import CollapsibleCard from '../components/CollapsibleCard';
import BlockedWordPresets from '../components/BlockedWordPresets';
import { TELEGRAM_PACKS } from '../data/blockedWordPacks';

function ProBadge() {
  return <Chip label="Pro" color="primary" size="small" sx={{ ml: 1, height: 18, fontSize: '0.65rem', fontWeight: 700 }} />;
}

function EntBadge() {
  return <Chip label="Enterprise" color="secondary" size="small" sx={{ ml: 1, height: 18, fontSize: '0.65rem', fontWeight: 700 }} />;
}

function DefaultTimezoneCard({ value, onChange }) {
  return (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        <Typography variant="subtitle1" fontWeight={600} mb={0.5}>Group Default Timezone</Typography>
        <Typography variant="body2" color="text.secondary" mb={2}>
          Saved per this group. All new scheduled items in this group use it automatically.
          You can still override the timezone per individual item.
        </Typography>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={6}>
            <TimezoneSelect value={value} onChange={onChange} label="Default Timezone" size="medium" />
          </Grid>
          <Grid item xs={12} sm={6}>
            <Typography variant="caption" color="text.secondary">
              Current time in this timezone:{' '}
              <strong>
                {new Date().toLocaleString('en-GB', {
                  timeZone: value || 'UTC',
                  year: 'numeric', month: '2-digit', day: '2-digit',
                  hour: '2-digit', minute: '2-digit', second: '2-digit',
                  hour12: false,
                })}
              </strong>
            </Typography>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
}

const ACTION_COLORS = {
  warn: 'warning', ban: 'error', kick: 'error', mute: 'warning',
  unmute: 'success', unban: 'success', tempban: 'error', tempmute: 'warning', purge: 'info',
};

// Inline moderation menu used in the Warnings + Audit Log rows so an admin can
// act on a repeat offender (warn / mute / kick / temp-ban / ban) without leaving
// the page. Single, owner-chosen target only — never bulk (anti-ban rule).
function ModerationActions({ botId, groupId, userId, username, onDone }) {
  const [anchor, setAnchor] = useState(null);
  const [busy, setBusy] = useState(false);
  const close = () => setAnchor(null);
  const LABELS = { warn: 'Warn', mute: 'Mute (1h)', kick: 'Kick', tempban: 'Temp-ban (24h)', ban: 'Ban permanently', unmute: 'Unmute', unban: 'Unban' };

  const run = async (action, opts = {}) => {
    close();
    if (!userId) { toast.error('No target user id on this row'); return; }
    const who = username ? `@${username}` : `user ${userId}`;
    if (action !== 'warn' && !window.confirm(`${LABELS[action]} ${who}?`)) return;
    setBusy(true);
    try {
      await settings.moderateMember(botId, groupId, userId, { action, ...opts });
      toast.success(`${LABELS[action]} applied to ${who}`);
      onDone?.();
    } catch (e) {
      toast.error(e.response?.data?.error || `Failed to ${action}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Tooltip title="Moderation actions">
        <span>
          <IconButton size="small" disabled={busy || !userId}
            onClick={(e) => { e.stopPropagation(); setAnchor(e.currentTarget); }}>
            {busy ? <CircularProgress size={16} /> : <Gavel fontSize="small" />}
          </IconButton>
        </span>
      </Tooltip>
      <Menu anchorEl={anchor} open={!!anchor} onClose={close} onClick={(e) => e.stopPropagation()}>
        <MenuItem onClick={() => run('warn')}>
          <ListItemIcon><WarningIcon fontSize="small" color="warning" /></ListItemIcon>
          <ListItemText>Warn</ListItemText>
        </MenuItem>
        <MenuItem onClick={() => run('mute', { duration_minutes: 60 })}>
          <ListItemIcon><VolumeOff fontSize="small" /></ListItemIcon>
          <ListItemText>Mute 1 hour</ListItemText>
        </MenuItem>
        <MenuItem onClick={() => run('kick')}>
          <ListItemIcon><PersonRemove fontSize="small" /></ListItemIcon>
          <ListItemText>Kick (remove)</ListItemText>
        </MenuItem>
        <Divider />
        <MenuItem onClick={() => run('tempban', { duration_minutes: 1440 })}>
          <ListItemIcon><Gavel fontSize="small" color="error" /></ListItemIcon>
          <ListItemText>Temp-ban 24h</ListItemText>
        </MenuItem>
        <MenuItem onClick={() => run('ban')}>
          <ListItemIcon><Block fontSize="small" color="error" /></ListItemIcon>
          <ListItemText>Ban permanently</ListItemText>
        </MenuItem>
        <Divider />
        {/* Reverse actions — lift a mute/ban applied by the bot or an admin. */}
        <MenuItem onClick={() => run('unmute')}>
          <ListItemIcon><VolumeUp fontSize="small" color="success" /></ListItemIcon>
          <ListItemText>Unmute (lift restriction)</ListItemText>
        </MenuItem>
        <MenuItem onClick={() => run('unban')}>
          <ListItemIcon><LockOpen fontSize="small" color="success" /></ListItemIcon>
          <ListItemText>Unban</ListItemText>
        </MenuItem>
      </Menu>
    </>
  );
}

// One AI Activity timeline row — shows a full preview (the answer for knowledge
// actions, the removed message for moderation) plus an Improve/Feedback control
// so an admin can correct the AI and, for answers, teach the bot for next time.
function AIActivityRow({ e, botId, groupId, fmtTs, onDone }) {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [saving, setSaving] = useState(false);
  const isKnowledge = e.category === 'knowledge';
  const meta = e.meta || {};
  const fb = meta.feedback || null;
  const [rating, setRating] = useState(fb?.rating || '');
  const [note, setNote] = useState(fb?.note || '');
  const [corrected, setCorrected] = useState(meta.answer || '');
  const [saveToKb, setSaveToKb] = useState(isKnowledge);

  const submit = async () => {
    setSaving(true);
    try {
      const res = await settings.submitAiActivityFeedback(botId, groupId, e.id, {
        rating,
        note,
        corrected_answer: isKnowledge ? corrected : '',
        save_to_kb: isKnowledge && saveToKb,
      });
      toast.success(res.data?.saved_to_kb
        ? 'Saved — the bot will use your improved answer next time'
        : 'Feedback saved');
      setOpen(false);
      onDone?.();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to save feedback');
    } finally {
      setSaving(false);
    }
  };

  return (
    <TableRow>
      <TableCell sx={{ whiteSpace: 'nowrap', verticalAlign: 'top', width: 150 }}>
        <Typography variant="caption" color="text.secondary">{fmtTs(e.created_at)}</Typography>
      </TableCell>
      <TableCell sx={{ verticalAlign: 'top', width: 110 }}>
        <Chip label={e.category} size="small" variant="outlined" sx={{ textTransform: 'capitalize' }} />
      </TableCell>
      <TableCell>
        <Box
          onClick={() => setExpanded((v) => !v)}
          sx={{ cursor: 'pointer', display: 'flex', alignItems: 'flex-start', gap: 0.5 }}
        >
          <Box component="span" sx={{ fontSize: '0.8rem', lineHeight: 1.4, color: 'text.secondary', mt: '1px' }}>
            {expanded ? '▾' : '▸'}
          </Box>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="body2" fontWeight={600}>
              {e.action}
              {e.status && e.status !== 'ok' && (
                <Chip label={e.status} size="small" color={e.status === 'failed' ? 'error' : 'default'} sx={{ ml: 1, height: 16, fontSize: '0.6rem' }} />
              )}
            </Typography>
            {e.target && <Typography variant="caption" color="text.secondary" display="block">{e.target}</Typography>}
            {/* Collapsed: one-line question/detail preview. Expanded: full Q + answer + message. */}
            {e.detail && (
              <Typography
                variant="caption" color="text.secondary" display="block"
                sx={expanded ? { whiteSpace: 'pre-wrap', wordBreak: 'break-word' }
                  : { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
              >
                {isKnowledge && expanded ? <><strong>Question:</strong> {e.detail}</> : e.detail}
              </Typography>
            )}
          </Box>
        </Box>
        {expanded && meta.answer && (
          <Typography variant="caption" color="text.primary" display="block" sx={{ mt: 0.5, ml: 2, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            <strong>AI answer:</strong> {meta.answer}
          </Typography>
        )}
        {expanded && meta.message && (
          <Typography variant="caption" color="text.disabled" display="block" sx={{ mt: 0.5, ml: 2, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            <strong>Message:</strong> {meta.message}
          </Typography>
        )}
        {expanded && !meta.answer && isKnowledge && (
          <Typography variant="caption" color="text.disabled" display="block" sx={{ mt: 0.5, ml: 2, fontStyle: 'italic' }}>
            (No stored answer — logged before answer capture, or no answer was sent.)
          </Typography>
        )}
        <Box sx={{ mt: 0.5, display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <Button size="small" variant="text" onClick={() => setOpen(true)} sx={{ fontSize: '0.68rem', minWidth: 0, p: 0.25 }}>
            {fb ? 'Edit feedback' : 'Improve / Feedback'}
          </Button>
          {fb?.rating && (
            <Chip size="small" variant="outlined"
              label={fb.rating === 'good' ? '👍 good' : '👎 needs work'}
              color={fb.rating === 'good' ? 'success' : 'warning'}
              sx={{ height: 18, fontSize: '0.6rem' }} />
          )}
        </Box>
      </TableCell>

      <Dialog open={open} onClose={() => !saving && setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Improve this AI action</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 2 }}>
          <Typography variant="body2" color="text.secondary">
            {e.action}{e.detail ? ` — ${e.detail}` : ''}
          </Typography>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button variant={rating === 'good' ? 'contained' : 'outlined'} color="success" size="small" onClick={() => setRating('good')}>👍 Good</Button>
            <Button variant={rating === 'bad' ? 'contained' : 'outlined'} color="warning" size="small" onClick={() => setRating('bad')}>👎 Needs work</Button>
          </Box>
          {isKnowledge && (
            <>
              <TextField label="Improved answer" fullWidth multiline minRows={3}
                value={corrected} onChange={(ev) => setCorrected(ev.target.value)}
                helperText="Edit the answer to be more accurate / professional." />
              <FormControlLabel
                control={<Switch checked={saveToKb} onChange={(ev) => setSaveToKb(ev.target.checked)} />}
                label="Teach the bot — save this Q→A so the next matching question uses it" />
            </>
          )}
          <TextField label="Note (optional)" fullWidth multiline minRows={2}
            value={note} onChange={(ev) => setNote(ev.target.value)}
            placeholder={isKnowledge ? 'Why was the answer wrong?' : 'e.g. this removal was a mistake — this kind of message is fine'} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)} disabled={saving}>Cancel</Button>
          <Button variant="contained" onClick={submit} disabled={saving || (!rating && !note.trim() && !corrected.trim())}>
            {saving ? <CircularProgress size={20} /> : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>
    </TableRow>
  );
}

// Friendly labels for the Protection Activity log (bot policy + raid mode).
const PROTECTION_EVENT_META = {
  bot_restricted:      { icon: '🤖', label: 'Bot restricted on join' },
  bot_banned:          { icon: '⛔', label: 'Unapproved bot banned' },
  bot_approved:        { icon: '✅', label: 'Bot approved' },
  bot_join_trusted:    { icon: '🟢', label: 'Trusted bot joined' },
  bot_join_unhandled:  { icon: '⚠️', label: 'Bot joined — needs review' },
  bot_join:            { icon: '🤖', label: 'Bot joined' },
  raid_mode_activated: { icon: '🚨', label: 'Raid mode activated' },
  raid_lockdown_join:  { icon: '🔒', label: 'Member locked down (raid)' },
};

const AUTOMOD_EXTENDED_RULES = [
  { key: 'contact_sharing', label: 'Block Contact Sharing' },
  { key: 'location_sharing', label: 'Block Location Sharing' },
  { key: 'email_detection', label: 'Block Email Addresses' },
  { key: 'spoiler_content', label: 'Block Spoiler Content' },
  { key: 'voice_notes', label: 'Block Voice Notes' },
  { key: 'video_notes', label: 'Block Video Notes (Circles)' },
  { key: 'file_attachments', label: 'Block File Attachments' },
  { key: 'photos', label: 'Block Photos' },
  { key: 'videos', label: 'Block Videos' },
  { key: 'gifs', label: 'Block GIFs / Animations' },
  { key: 'stickers', label: 'Block Stickers' },
  { key: 'games', label: 'Block Games' },
  { key: 'bot_mentions', label: 'Block Bot Mentions' },
];

const LANGUAGE_OPTIONS = [
  { value: 'cyrillic', label: 'Cyrillic (Russian, Ukrainian…)' },
  { value: 'chinese', label: 'Chinese' },
  { value: 'korean', label: 'Korean' },
  { value: 'arabic', label: 'Arabic' },
  { value: 'hindi', label: 'Hindi' },
  { value: 'japanese', label: 'Japanese' },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function parseTopicInput(val) {
  if (!val || !val.trim()) return null;
  const match = val.match(/\/(\d+)\/?$/);
  if (match) return parseInt(match[1], 10);
  const n = parseInt(val, 10);
  return isNaN(n) ? null : n;
}

function classifyReason(reason) {
  if (!reason) return null;
  const r = reason.toLowerCase();
  if (r.includes('telegizer') || r.includes('tracked link')) return { label: 'Telegizer link', color: 'info' };
  if (r.includes('t.me/+') || r.includes('t.me/joinchat')) return { label: 'Telegram invite', color: 'warning' };
  if (r.includes('t.me/') || r.includes('telegram.me/')) return { label: 'Telegram link', color: 'warning' };
  if (r.includes('link') || r.includes('invite')) return { label: 'External link', color: 'default' };
  return null;
}


function getMessagePreview(log) {
  const meta = log.metadata;
  const extra = log.extra_data;
  if (meta) return meta.message_text || meta.text || meta.message || null;
  if (extra) return extra.message_text || extra.text || extra.message || null;
  return null;
}

function formatMsgPreview(text, maxLen = 150) {
  if (!text) return null;
  const clean = text.replace(/\s+/g, ' ').trim();
  return clean.length > maxLen ? clean.slice(0, maxLen) + '…' : clean;
}

function categorizeReason(reason) {
  if (!reason) return '—';
  const r = reason.toLowerCase();
  if (r.includes('t.me/+') || r.includes('joinchat') || (r.includes('invite') && r.includes('link'))) return 'Invite link';
  if (r.includes('telegizer') || r.includes('tracked link')) return 'Telegizer link';
  if (r.includes('t.me/') || r.includes('telegram.me/')) return 'Telegram link';
  if (r.includes('http') || r.includes('external link') || r.includes('url')) return 'External link';
  if (r.includes('spam') || r.includes('promotional') || r.includes('adverti')) return 'Spam';
  if (r.includes('unrelated') || r.includes('off-topic') || r.includes('off topic') || r.includes('different community') || r.includes('not related')) return 'Off-topic';
  if (r.includes('bad word') || r.includes('profanity') || r.includes('inappropriate language')) return 'Bad words';
  if (r.includes('caps') || r.includes('uppercase')) return 'Caps lock';
  if (r.includes('forward')) return 'Forwarded msg';
  if (r.includes('emoji')) return 'Excessive emojis';
  if (r.includes('link')) return 'Contains link';
  const dashIdx = reason.indexOf(' — ');
  const base = dashIdx !== -1 ? reason.slice(dashIdx + 3) : reason;
  const dotIdx = base.indexOf('. ');
  if (dotIdx > 0 && dotIdx < 55) return base.slice(0, dotIdx);
  return base.slice(0, 38) + (base.length > 38 ? '…' : '');
}

// ── Command Routing Tab Component ─────────────────────────────────────────────

const SCOPE_OPTIONS = [
  { value: 'all_group', label: 'Works everywhere' },
  { value: 'specific_topics', label: 'Only selected topics' },
  { value: 'disabled', label: 'Disabled' },
];

// CommandRoutingTab removed — replaced by InlineCmdRouting blocks per-section
// and Command Permissions dropdowns in Moderation tab.


// ── Reusable inline command routing block ─────────────────────────────────────
// Renders a compact scope selector + topic picker for each command in `cmds`.
// Share the same cmdRouting state + handleSaveCmdRouting from GroupSettings.
function InlineCmdRouting({ id, cmds, title, description, cmdRouting, setCmdRouting, saving, onSave }) {
  const topics = cmdRouting.topics || [];
  return (
    <CollapsibleCard id={id} title={title || 'Command Routing'}>
        {description && (
          <Typography variant="body2" color="text.secondary" mb={2}>{description}</Typography>
        )}
        <Divider sx={{ mb: 2 }} />
        {cmds.map((cmd) => {
          const rule = (cmdRouting.commands || {})[cmd] || { scope: 'all_group', topic_ids: [] };
          return (
            <Box key={cmd} sx={{ mb: 2 }}>
              <Stack direction={{ xs: 'column', sm: 'row' }} alignItems={{ xs: 'stretch', sm: 'center' }} spacing={{ xs: 1, sm: 2 }} mb={1}>
                <Typography fontWeight={600} sx={{ minWidth: { sm: 130 }, fontFamily: 'monospace' }}>{cmd}</Typography>
                <FormControl size="small" sx={{ minWidth: 200, width: { xs: '100%', sm: 'auto' } }}>
                  <InputLabel>Access</InputLabel>
                  <Select
                    value={rule.scope}
                    label="Access"
                    onChange={(e) => {
                      setCmdRouting((prev) => ({
                        ...prev,
                        commands: { ...prev.commands, [cmd]: { ...rule, scope: e.target.value } },
                      }));
                    }}
                  >
                    {SCOPE_OPTIONS.map((o) => (
                      <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Stack>
              {rule.scope === 'specific_topics' && (
                <Box sx={{ ml: 0.5 }}>
                  {topics.length === 0 ? (
                    <TextField
                      size="small"
                      fullWidth
                      label="Topic ID or link"
                      placeholder="e.g. 12345 or https://t.me/c/123/456"
                      value={rule.manual_topic_input || (rule.topic_ids?.[0] ? String(rule.topic_ids[0]) : '')}
                      onChange={(e) => {
                        const raw = e.target.value;
                        const parsed = parseTopicInput(raw);
                        setCmdRouting((prev) => ({
                          ...prev,
                          commands: {
                            ...prev.commands,
                            [cmd]: { ...rule, manual_topic_input: raw, topic_ids: parsed ? [String(parsed)] : [] },
                          },
                        }));
                      }}
                      helperText="No forum topics detected yet. Paste a topic link or enter the topic ID directly."
                    />
                  ) : (
                    <Stack direction="row" flexWrap="wrap" gap={1}>
                      {topics.map((t) => {
                        const checked = (rule.topic_ids || []).includes(String(t.thread_id));
                        return (
                          <FormControlLabel
                            key={t.thread_id}
                            control={
                              <Switch
                                size="small"
                                checked={checked}
                                onChange={(e) => {
                                  const current = rule.topic_ids || [];
                                  const updated = e.target.checked
                                    ? [...new Set([...current, String(t.thread_id)])]
                                    : current.filter((id) => id !== String(t.thread_id));
                                  setCmdRouting((prev) => ({
                                    ...prev,
                                    commands: { ...prev.commands, [cmd]: { ...rule, topic_ids: updated } },
                                  }));
                                }}
                              />
                            }
                            label={t.name}
                          />
                        );
                      })}
                    </Stack>
                  )}
                </Box>
              )}
            </Box>
          );
        })}
        <Button variant="contained" size="small" disabled={saving} onClick={onSave} sx={{ mt: 1 }}>
          {saving ? <CircularProgress size={16} sx={{ mr: 1 }} /> : null}
          Save Routing
        </Button>
    </CollapsibleCard>
  );
}

export default function GroupSettings() {
  return (
    <UiPrefsProvider>
      <GroupSettingsInner />
    </UiPrefsProvider>
  );
}

function GroupSettingsInner() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const navigate = useNavigate();
  const { requestHighlight } = useUiPrefs();
  const { id: rawBotId, groupId } = useParams();
  const botId = rawBotId || 'official';
  const isOfficial = !rawBotId;

  const CATEGORIES = buildCategories(isOfficial);

  const [cat, setCat] = useState('moderation');
  const [subTab, setSubTab] = useState(0);
  const [groupData, setGroupData] = useState(null);
  const [settingsData, setSettingsData] = useState(null);
  const [trustedBotInput, setTrustedBotInput] = useState('');
  const [allowlistInput, setAllowlistInput] = useState('');
  // Snapshot of last-saved settings (JSON string) — used to enable Save only when dirty (#12)
  const [origSettings, setOrigSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [members, setMembers] = useState([]);
  const [, setMembersTotal] = useState(0);
  const [membersPage, setMembersPage] = useState(1);
  const [membersPages, setMembersPages] = useState(1);
  const [membersSearch, setMembersSearch] = useState('');
  const [membersSort, setMembersSort] = useState('xp');
  const [membersTimeRange, setMembersTimeRange] = useState('all');

  const [leaderboard, setLeaderboard] = useState([]);
  const [leaderboardLoading, setLeaderboardLoading] = useState(false);
  const [leaderboardTimeRange, setLeaderboardTimeRange] = useState('all');
  const [leaderboardWalletOnly, setLeaderboardWalletOnly] = useState(false);
  const [leaderboardSearch, setLeaderboardSearch] = useState('');

  const [auditLogs, setAuditLogs] = useState([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditPage, setAuditPage] = useState(1);
  const [auditSearch, setAuditSearch] = useState('');
  const [expandedLogId, setExpandedLogId] = useState(null);
  const [expandedWarnId, setExpandedWarnId] = useState(null);

  const [autoResponses, setAutoResponses] = useState([]);
  const [arDialogOpen, setArDialogOpen] = useState(false);
  const [arForm, setArForm] = useState({ trigger_text: '', response_text: '', match_type: 'contains', is_case_sensitive: false });
  const [arSaving, setArSaving] = useState(false);

  const [reports, setReports] = useState([]);
  const [reportsLoading, setReportsLoading] = useState(false);
  const [reportAdminAnchor, setReportAdminAnchor] = useState(null);

  // Warnings — official groups only
  const [warnings, setWarnings] = useState([]);
  const [warningsLoading, setWarningsLoading] = useState(false);
  const [warningsSearch, setWarningsSearch] = useState('');
  const [warningsTotal, setWarningsTotal] = useState(0);
  const [warningsActiveTotal, setWarningsActiveTotal] = useState(0);
  const [warningsPage, setWarningsPage] = useState(1);
  const WARN_PER_PAGE = 50;

  const [raidOpen, setRaidOpen] = useState(false);

  // Protection Activity (bot policy + raid mode event log) — Moderation › AutoMod
  const [protectionLog, setProtectionLog] = useState([]);
  const [protectionLoading, setProtectionLoading] = useState(false);
  const [emergencyMins, setEmergencyMins] = useState(60);

  const [digestConfig, setDigestConfig] = useState({
    daily: false, weekly: false, monthly: false,
    recipients: { owner_dm: false, selected_admin_ids: [], send_to_group: true, group_topic_id: null },
  });
  const [digestLoading, setDigestLoading] = useState(false);
  const [digestSaving, setDigestSaving] = useState(false);
  const [digestSending, setDigestSending] = useState('');

  // AI Activity tab
  const [aiActivity, setAiActivity] = useState({ metrics: {}, by_category: {}, events: [] });
  const [aiActivityLoading, setAiActivityLoading] = useState(false);
  const [aiActivityCategory, setAiActivityCategory] = useState('');
  const [aiStatus, setAiStatus] = useState(null);

  // Admin list for reports / digest recipient selection
  const [groupAdmins, setGroupAdmins] = useState([]);
  const [adminsLoading, setAdminsLoading] = useState(false);

  // Command routing / topic access control
  const [cmdRouting, setCmdRouting] = useState({ topics: [], commands: {}, restricted_reply: 'silent', restricted_message: '⚠️ This command is only available in the {topic} topic.' });
  const [routingSaving, setRoutingSaving] = useState(false);

  const [userTier] = useState(() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}').subscription_tier || 'free'; }
    catch { return 'free'; }
  });

  const isMounted = React.useRef(true);
  React.useEffect(() => {
    isMounted.current = true;
    return () => { isMounted.current = false; };
  }, []);

  const fetchSettings = useCallback(async () => {
    setLoading(true);
    try {
      const res = await settings.getGroupSettings(botId, groupId);
      if (!isMounted.current) return;
      setGroupData(res.data.group);
      setSettingsData(res.data.settings);
      setOrigSettings(JSON.stringify(res.data.settings || {}));
    } catch {
      if (!isMounted.current) return;
      toast.error('Failed to load settings');
      navigate(isOfficial ? '/groups' : `/bot/${botId}`);
    } finally {
      if (isMounted.current) setLoading(false);
    }
  }, [botId, groupId, navigate, isOfficial]);

  const fetchMembers = useCallback(async (page = 1) => {
    try {
      const params = { page, per_page: 20 };
      if (membersSearch) params.q = membersSearch;
      if (membersTimeRange && membersTimeRange !== 'all') params.period = membersTimeRange;
      params.sort_by = membersSort;
      params.sort_dir = 'desc';
      const res = await settings.getMembers(botId, groupId, params);
      setMembers(res.data.members);
      setMembersTotal(res.data.total || 0);
      setMembersPages(res.data.pages || 1);
    } catch {
      toast.error('Failed to load members');
    }
  }, [botId, groupId, membersSearch, membersTimeRange, membersSort]);

  const exportMembersCSV = useCallback(() => {
    if (!members.length) return;
    const xpField = { '1d': 'xp_1d', '7d': 'xp_7d', '30d': 'xp_30d' }[membersTimeRange] || 'xp';
    const xpLabel = membersTimeRange === '1d' ? 'XP (Today)' : membersTimeRange === '7d' ? 'XP (7d)' : membersTimeRange === '30d' ? 'XP (30d)' : 'XP';
    const headers = ['Name', 'Username', 'Telegram ID', xpLabel, 'Level', 'Warnings', 'Role', 'Verified', 'Wallet Submitted', 'Wallet Address'];
    const rows = members.map(m => [
      m.first_name || '',
      m.username ? `@${m.username}` : '',
      m.telegram_user_id || m.user_id || m.id || '',
      m[xpField] ?? 0,
      m.level ?? 0,
      m.warnings ?? 0,
      m.role || '',
      m.is_verified ? 'Yes' : 'No',
      m.wallet_address ? 'Yes' : 'No',
      m.wallet_address || '',
    ]);
    const csv = [headers, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `members_${groupId}.csv`; a.click();
    URL.revokeObjectURL(url);
  }, [members, groupId, membersTimeRange]);

  const exportLeaderboardCSV = useCallback(() => {
    if (!leaderboard.length) return;
    const xpField = { '1d': 'xp_1d', '7d': 'xp_7d', '30d': 'xp_30d' }[leaderboardTimeRange] || 'xp';
    const xpLabel = leaderboardTimeRange === '1d' ? 'XP (Today)' : leaderboardTimeRange === '7d' ? 'XP (7d)' : leaderboardTimeRange === '30d' ? 'XP (30d)' : 'XP (All Time)';
    const headers = ['Rank', 'Name', 'Username', xpLabel, 'Level', 'Role', 'Wallet Address'];
    const rows = leaderboard.map((m, i) => [
      i + 1,
      m.first_name || '',
      m.username ? `@${m.username}` : '',
      m[xpField] ?? 0,
      m.level ?? 0,
      m.role || '',
      m.wallet_address || '',
    ]);
    const csv = [headers, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `leaderboard_${groupId}_${leaderboardTimeRange}.csv`; a.click();
    URL.revokeObjectURL(url);
  }, [leaderboard, groupId, leaderboardTimeRange]);

  const fetchLeaderboard = useCallback(async () => {
    setLeaderboardLoading(true);
    try {
      const params = { limit: 50 };
      if (leaderboardTimeRange && leaderboardTimeRange !== 'all') params.period = leaderboardTimeRange;
      if (leaderboardWalletOnly) params.has_wallet = 'true';
      if (leaderboardSearch.trim()) params.q = leaderboardSearch.trim();
      const res = await settings.getLeaderboard(botId, groupId, params);
      setLeaderboard(res.data.members || []);
    } catch {
      toast.error('Failed to load leaderboard');
    } finally {
      setLeaderboardLoading(false);
    }
  }, [botId, groupId, leaderboardTimeRange, leaderboardWalletOnly, leaderboardSearch]);

  const fetchAuditLogs = useCallback(async (page = 1) => {
    try {
      const params = { page, per_page: 20 };
      if (auditSearch.trim()) params.q = auditSearch.trim();
      const res = await settings.getAuditLogs(botId, groupId, params);
      setAuditLogs(res.data.logs);
      setAuditTotal(res.data.pages);
    } catch {
      toast.error('Failed to load audit logs');
    }
  }, [botId, groupId, auditSearch]);

  const fetchProtectionLog = useCallback(async () => {
    setProtectionLoading(true);
    try {
      const res = await settings.getProtectionLog(botId, groupId, { per_page: 30 });
      setProtectionLog(res.data.events || []);
    } catch {
      // Non-fatal: the card just shows the empty state.
      setProtectionLog([]);
    } finally {
      setProtectionLoading(false);
    }
  }, [botId, groupId]);

  const fetchAutoResponses = useCallback(async () => {
    try {
      const res = await settings.getAutoResponses(botId, groupId);
      setAutoResponses(res.data.auto_responses);
    } catch {
      toast.error('Failed to load auto-responses');
    }
  }, [botId, groupId]);

  const fetchReports = useCallback(async () => {
    setReportsLoading(true);
    try {
      const res = await settings.getReports(botId, groupId);
      setReports(res.data.reports);
    } catch {
      toast.error('Failed to load reports');
    } finally {
      setReportsLoading(false);
    }
  }, [botId, groupId]);

  const fetchWarnings = useCallback(async (opts = {}) => {
    const page = opts.page || 1;
    const search = opts.search !== undefined ? opts.search : warningsSearch;
    setWarningsLoading(true);
    try {
      const res = await settings.listWarnings(botId, groupId, {
        search: search || undefined, page, per_page: WARN_PER_PAGE,
      });
      const rows = res.data.warnings || [];
      setWarnings((prev) => (page > 1 ? [...prev, ...rows] : rows));
      setWarningsTotal(res.data.total ?? rows.length);
      setWarningsActiveTotal(res.data.active_total ?? res.data.total ?? rows.length);
      setWarningsPage(page);
    } catch {
      toast.error('Failed to load warnings');
    } finally {
      setWarningsLoading(false);
    }
  }, [botId, groupId, warningsSearch]);

  // Server-side search: debounce the query so it searches ALL warnings (every
  // page), not just the rows currently loaded client-side.
  useEffect(() => {
    if (!(cat === 'analytics' && subTab === warningsSubTabIdx)) return undefined;
    const t = setTimeout(() => { fetchWarnings({ page: 1, search: warningsSearch }); }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [warningsSearch]);

  const handleRemoveWarning = async (warningId) => {
    try {
      await settings.removeWarning(botId, groupId, warningId);
      toast.success('Warning removed');
      setWarnings(prev => prev.filter(w => w.id !== warningId));
    } catch {
      toast.error('Failed to remove warning');
    }
  };

  const fetchDigest = useCallback(async () => {
    setDigestLoading(true);
    try {
      const res = await digestApi.get(botId, groupId);
      setDigestConfig(prev => ({
        ...prev,
        ...res.data.digest,
        recipients: { owner_dm: false, selected_admin_ids: [], send_to_group: true, group_topic_id: null, ...(res.data.digest?.recipients || {}) },
      }));
    } catch {
      // digest not yet configured — use defaults
    } finally {
      setDigestLoading(false);
    }
  }, [botId, groupId]);

  const fetchAIActivity = useCallback(async () => {
    setAiActivityLoading(true);
    try {
      const [act, st] = await Promise.all([
        settings.getAIActivity(botId, groupId, { page: 1, category: aiActivityCategory || undefined }),
        settings.getAIStatus(botId, groupId).catch(() => ({ data: null })),
      ]);
      setAiActivity(act.data || { metrics: {}, by_category: {}, events: [] });
      setAiStatus(st.data || null);
    } catch {
      setAiActivity({ metrics: {}, by_category: {}, events: [] });
    } finally {
      setAiActivityLoading(false);
    }
  }, [botId, groupId, aiActivityCategory]);

  const fetchAdmins = useCallback(async () => {
    setAdminsLoading(true);
    try {
      const res = await settings.getGroupAdmins(botId, groupId);
      setGroupAdmins(res.data.admins || []);
    } catch {
      setGroupAdmins([]);
    } finally {
      setAdminsLoading(false);
    }
  }, [botId, groupId]);

  const handleSaveDigest = async () => {
    setDigestSaving(true);
    try {
      const res = await digestApi.update(botId, groupId, {
        daily: digestConfig.daily,
        weekly: digestConfig.weekly,
        monthly: digestConfig.monthly,
        recipients: digestConfig.recipients,
      });
      if (res.data?.digest) {
        setDigestConfig(prev => ({
          ...prev,
          ...res.data.digest,
          recipients: {
            owner_dm: false,
            selected_admin_ids: [],
            send_to_group: true,
            group_topic_id: null,
            ...(res.data.digest?.recipients || {}),
          },
        }));
      }
      toast.success('Digest settings saved!');
    } catch {
      toast.error('Failed to save digest settings');
    } finally {
      setDigestSaving(false);
    }
  };

  const handleSendNow = async (period) => {
    setDigestSending(period);
    try {
      await digestApi.sendNow(botId, groupId, { period });
      toast.success(`${period.charAt(0).toUpperCase() + period.slice(1)} report sent to configured recipients!`);
      fetchDigest();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to send report');
    } finally {
      setDigestSending('');
    }
  };

  const fetchCmdRouting = useCallback(async () => {
    try {
      let res;
      if (isOfficial) {
        res = await settings.getCommandRouting(botId, groupId);
      } else {
        res = await settings.getCustomCommandRouting(botId, groupId);
      }
      setCmdRouting(res.data.routing || { topics: [], commands: {}, restricted_reply: 'silent', restricted_message: '⚠️ This command is only available in the {topic} topic.' });
    } catch {
      // silently ignore — feature just won't show routing data
    }
  }, [botId, groupId, isOfficial]);

  const handleSaveCmdRouting = async () => {
    setRoutingSaving(true);
    try {
      if (isOfficial) {
        await settings.updateCommandRouting(botId, groupId, cmdRouting);
      } else {
        await settings.updateCustomCommandRouting(botId, groupId, cmdRouting);
      }
      toast.success('Command routing saved!');
    } catch {
      toast.error('Failed to save command routing');
    } finally {
      setRoutingSaving(false);
    }
  };

  // SubTab indices are derived from the feature registry — no hardcoding needed.
  // getSubTabIndex returns -1 for officialOnly subtabs in custom-bot context,
  // which safely disables the associated useEffect guards.
  const leaderboardSubTabIdx  = getSubTabIndex(CATEGORIES, 'analytics', 'Leaderboard');
  const auditLogSubTabIdx     = getSubTabIndex(CATEGORIES, 'analytics', 'Audit Log');
  const warningsSubTabIdx     = getSubTabIndex(CATEGORIES, 'analytics', 'Warnings');
  const digestSubTabIdx       = getSubTabIndex(CATEGORIES, 'analytics', 'Digest');
  const aiActivitySubTabIdx   = getSubTabIndex(CATEGORIES, 'analytics', 'AI Activity');
  // Automation + AI subtab indices (derived — Forwarding/Workflows/Webhooks were
  // appended and Webhooks moved out of AI, so positional guards are unsafe).
  const autoReplySubTabIdx    = getSubTabIndex(CATEGORIES, 'automation', 'Auto Reply');
  const pollsSubTabIdx        = getSubTabIndex(CATEGORIES, 'automation', 'Polls');
  const forwardingSubTabIdx   = getSubTabIndex(CATEGORIES, 'automation', 'Forwarding');
  const workflowsSubTabIdx    = getSubTabIndex(CATEGORIES, 'automation', 'Workflows');
  const webhooksSubTabIdx     = getSubTabIndex(CATEGORIES, 'automation', 'Webhooks');
  const escalationSubTabIdx   = getSubTabIndex(CATEGORIES, 'ai', 'Escalation');
  // Telegram chat id of this group — forwarding/workflows key on it.
  const groupChatId = groupData?.telegram_group_id || groupId;
  const groupDisplayName = groupData?.title || groupData?.group_name || groupData?.name || null;
  useEffect(() => { fetchSettings(); }, [fetchSettings]);
  useEffect(() => { if (cat === 'analytics' && subTab === 0) fetchMembers(membersPage); }, [cat, subTab, membersPage, fetchMembers]);
  useEffect(() => { if (cat === 'analytics' && subTab === leaderboardSubTabIdx) fetchLeaderboard(); }, [cat, subTab, leaderboardSubTabIdx, fetchLeaderboard]);
  useEffect(() => { if (cat === 'analytics' && subTab === auditLogSubTabIdx) fetchAuditLogs(auditPage); }, [cat, subTab, auditLogSubTabIdx, auditPage, fetchAuditLogs]);
  useEffect(() => { if (cat === 'automation' && subTab === autoReplySubTabIdx) fetchAutoResponses(); }, [cat, subTab, autoReplySubTabIdx, fetchAutoResponses]);
  useEffect(() => { if (cat === 'moderation' && subTab === 2) fetchReports(); }, [cat, subTab, fetchReports]);
  useEffect(() => { if (cat === 'moderation' && subTab === 0) fetchProtectionLog(); }, [cat, subTab, fetchProtectionLog]);
  useEffect(() => { if (cat === 'analytics' && subTab === warningsSubTabIdx) fetchWarnings(); }, [cat, subTab, warningsSubTabIdx, fetchWarnings]);
  useEffect(() => { if (cat === 'analytics' && subTab === digestSubTabIdx) fetchDigest(); }, [cat, subTab, digestSubTabIdx, fetchDigest]);
  useEffect(() => { if (cat === 'analytics' && subTab === aiActivitySubTabIdx) fetchAIActivity(); }, [cat, subTab, aiActivitySubTabIdx, fetchAIActivity]);
  useEffect(() => {
    if ((cat === 'moderation' && subTab === 2) || (cat === 'analytics' && subTab === digestSubTabIdx) || (cat === 'ai' && subTab === escalationSubTabIdx)) {
      fetchAdmins();
    }
  }, [cat, subTab, digestSubTabIdx, escalationSubTabIdx, fetchAdmins]);
  useEffect(() => { fetchCmdRouting(); }, [fetchCmdRouting]);

  const [upgradeModalOpen, setUpgradeModalOpen] = useState(false);
  const [upgradeFeature, setUpgradeFeature] = useState('');

  const handleSave = async () => {
    setSaving(true);
    try {
      await settings.updateGroupSettings(botId, groupId, settingsData);
      setOrigSettings(JSON.stringify(settingsData || {}));
      toast.success('Settings saved!');
      track('first_moderation_rule_set', { bot_id: botId, group_id: groupId });
    } catch (err) {
      if (err.response?.status === 403 && err.response?.data?.code === 'FEATURE_REQUIRES_PRO') {
        setUpgradeFeature(err.response.data.feature || 'This feature');
        setUpgradeModalOpen(true);
      } else {
        toast.error(err.response?.data?.error || 'Failed to save settings');
      }
    } finally {
      setSaving(false);
    }
  };

  // Emergency lockdown — persists raid_guard.manual_lockdown_until and saves
  // immediately (it's a panic button, not a deferred setting). minutes=null lifts.
  const setEmergencyLockdown = async (minutes) => {
    const until = minutes ? new Date(Date.now() + minutes * 60000).toISOString() : null;
    const patched = {
      ...settingsData,
      raid_guard: { ...(settingsData?.raid_guard || {}), manual_lockdown_until: until },
    };
    setSaving(true);
    try {
      await settings.updateGroupSettings(botId, groupId, patched);
      setSettingsData(patched);
      setOrigSettings(JSON.stringify(patched));
      toast.success(minutes ? 'Emergency lockdown activated' : 'Lockdown lifted');
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to update lockdown');
    } finally {
      setSaving(false);
    }
  };

  const addTrustedBot = () => {
    const uname = (trustedBotInput || '').trim().replace(/^@/, '').toLowerCase();
    if (!uname) return;
    const current = (settingsData?.bot_policy?.trusted_bot_usernames) || [];
    if (!current.includes(uname)) {
      updateSetting('bot_policy.trusted_bot_usernames', [...current, uname]);
    }
    setTrustedBotInput('');
  };

  const addAllowlistEntry = () => {
    const token = (allowlistInput || '').trim().replace(/^@/, '');
    if (!token) return;
    const normalized = /^-?\d+$/.test(token) ? token : token.toLowerCase();
    const current = (settingsData?.automod?.allowlist) || [];
    if (!current.includes(normalized)) {
      updateSetting('automod.allowlist', [...current, normalized]);
    }
    setAllowlistInput('');
  };

  const updateSetting = (path, value) => {
    // Proactively block free users from enabling Pro-gated sections
    // (backend also enforces this on save, but intercepting early gives instant feedback)
    if (value === true) {
      const topKey = path.split('.')[0];
      try {
        const user = JSON.parse(localStorage.getItem('user') || '{}');
        if (user.subscription_tier === 'free' && PRO_GATED_SECTIONS.has(topKey)) {
          setUpgradeFeature(PRO_GATED_LABELS[topKey] || topKey);
          setUpgradeModalOpen(true);
          return;
        }
      } catch { /* ignore */ }
    }
    const keys = path.split('.');
    setSettingsData((prev) => {
      const updated = { ...prev };
      let obj = updated;
      for (let i = 0; i < keys.length - 1; i++) {
        obj[keys[i]] = { ...obj[keys[i]] };
        obj = obj[keys[i]];
      }
      obj[keys[keys.length - 1]] = value;
      return updated;
    });
  };

  const handleCreateAutoResponse = async () => {
    if (!arForm.trigger_text || !arForm.response_text) {
      toast.error('Trigger and response are required');
      return;
    }
    setArSaving(true);
    try {
      await settings.createAutoResponse(botId, groupId, arForm);
      toast.success('Auto-response created');
      setArDialogOpen(false);
      setArForm({ trigger_text: '', response_text: '', match_type: 'contains', is_case_sensitive: false });
      fetchAutoResponses();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to create');
    } finally {
      setArSaving(false);
    }
  };

  const handleDeleteAutoResponse = async (arId) => {
    try {
      await settings.deleteAutoResponse(botId, groupId, arId);
      toast.success('Deleted');
      fetchAutoResponses();
    } catch {
      toast.error('Failed to delete');
    }
  };

  const handleToggleAutoResponse = async (ar) => {
    try {
      await settings.updateAutoResponse(botId, groupId, ar.id, { is_enabled: !ar.is_enabled });
      fetchAutoResponses();
    } catch {
      toast.error('Failed to update');
    }
  };

  const handleToggleAiKnowledge = async (ar) => {
    try {
      await settings.updateAutoResponse(botId, groupId, ar.id, { use_as_ai_knowledge: !ar.use_as_ai_knowledge });
      fetchAutoResponses();
    } catch {
      toast.error('Failed to update');
    }
  };

  const handleResolveReport = async (reportId) => {
    try {
      await settings.resolveReport(botId, groupId, reportId);
      toast.success('Report resolved');
      fetchReports();
    } catch {
      toast.error('Failed to resolve report');
    }
  };

  const handleCatChange = (newCat) => {
    setCat(newCat);
    setSubTab(0);
  };

  if (loading || !settingsData) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  const v = settingsData.verification || {};
  const w = settingsData.welcome || {};
  const l = settingsData.levels || {};
  const am = settingsData.automod || {};
  const bp = settingsData.bot_policy || {};
  const rg = settingsData.raid_guard || {};
  const mod = settingsData.moderation || {};
  const sm = am.slow_mode || {};
  const ac = settingsData.auto_clean || {};
  const rep = settingsData.reports || {};
  const we = settingsData.warning_escalation || {};

  const currentCat = CATEGORIES.find((c) => c.id === cat);

  // #12 — Save is enabled only when the user has actually changed something.
  const isDirty = settingsData != null && origSettings != null
    && JSON.stringify(settingsData) !== origSettings;

  // #13 — format timestamps in the group's configured timezone (not the browser's),
  // so every screen on this page reads consistently.
  const groupTz = settingsData?.timezone || 'UTC';
  const fmtTs = (ts, opts = { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) => {
    if (!ts) return '—';
    try {
      return new Date(ts).toLocaleString([], { ...opts, timeZone: groupTz });
    } catch {
      return new Date(ts).toLocaleString();
    }
  };

  // #5 — AI Status cards link to the exact tab AND card where each thing is
  // configured, then briefly highlight that card so it's obvious.
  const aiStatusTargets = {
    'Smart Moderation': { cat: 'moderation', sub: getSubTabIndex(CATEGORIES, 'moderation', 'AutoMod'),         card: 'tg.moderation.smart_moderation' },
    'AI Integrations':  { cat: 'ai',         sub: getSubTabIndex(CATEGORIES, 'ai', 'Knowledge Base'),          card: 'tg.ai.reply_personality' },
    'Knowledge Base':   { cat: 'ai',         sub: getSubTabIndex(CATEGORIES, 'ai', 'Knowledge Base'),          card: 'tg.ai.knowledge_base' },
    'OpenAI Provider':  { cat: 'ai',         sub: getSubTabIndex(CATEGORIES, 'ai', 'Knowledge Base'),          card: 'tg.ai.knowledge_base' },
  };
  const goToTarget = (t) => {
    if (!t) return;
    setCat(t.cat);
    setSubTab(t.sub >= 0 ? t.sub : 0);
    if (t.card) {
      // Let the tab content mount before opening + highlighting + scrolling.
      setTimeout(() => requestHighlight(t.card), 120);
    } else {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>

      {/* Upgrade required modal */}
      <Dialog open={upgradeModalOpen} onClose={() => setUpgradeModalOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Pro Feature Required</DialogTitle>
        <DialogContent>
          <Typography variant="body2" gutterBottom>
            <strong>{upgradeFeature}</strong> is available on the Pro and Enterprise plans.
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Upgrade to unlock advanced moderation, scheduled content, analytics, AI knowledge base, and more.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setUpgradeModalOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={() => { setUpgradeModalOpen(false); navigate('/pricing'); }}>
            View Plans
          </Button>
        </DialogActions>
      </Dialog>

      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar>
          <IconButton edge="start" onClick={() => navigate(isOfficial ? '/groups' : `/bot/${botId}`)} sx={{ mr: 1 }}>
            <ArrowBack />
          </IconButton>
          {/* Breadcrumb nav links — hidden on mobile (back arrow handles the
              "up" action there) to keep the header to a single compact row. */}
          <Box sx={{ display: { xs: 'none', md: 'flex' }, alignItems: 'center', gap: 0.5, mr: 1 }}>
            <Button size="small" variant="text" onClick={() => navigate('/dashboard')} sx={{ fontSize: '0.75rem', px: 1, py: 0.25, minWidth: 0, color: 'text.secondary' }}>
              Dashboard
            </Button>
            <Box component="span" sx={{ color: 'text.disabled', fontSize: '0.75rem' }}>/</Box>
            <Button size="small" variant="text" onClick={() => navigate(isOfficial ? '/groups' : `/bot/${botId}`)} sx={{ fontSize: '0.75rem', px: 1, py: 0.25, minWidth: 0, color: 'text.secondary' }}>
              {isOfficial ? 'My Groups' : 'Bot Settings'}
            </Button>
            <Box component="span" sx={{ color: 'text.disabled', fontSize: '0.75rem' }}>/</Box>
          </Box>
          <Typography variant="h6" fontWeight={600} sx={{ flexGrow: 1 }} noWrap>
            {groupData?.group_name || groupData?.title || 'Group Settings'}
          </Typography>
          {settingsData && (
            <Tooltip title="Group default timezone — change it in Automation › Scheduler">
              <Chip
                icon={<Schedule sx={{ fontSize: 14 }} />}
                label={settingsData.timezone || 'UTC'}
                size="small"
                variant="outlined"
                sx={{ mr: 1.5, fontSize: 11, color: 'inherit', borderColor: 'rgba(255,255,255,0.4)', cursor: 'default', display: { xs: 'none', sm: 'inline-flex' } }}
              />
            </Tooltip>
          )}
          <Button
            variant="contained"
            startIcon={saving ? <CircularProgress size={16} color="inherit" /> : <Save />}
            onClick={handleSave}
            disabled={saving || cat === 'analytics' || !isDirty}
          >
            {saving ? 'Saving…' : isDirty ? 'Save' : 'Saved'}
          </Button>
        </Toolbar>

        {/* Category pill nav — fade gradient on right edge signals horizontal scroll */}
        <Box sx={{ position: 'relative' }}>
          <Box sx={{
            position: 'absolute', right: 0, top: 0, bottom: 0, width: 32, zIndex: 1, pointerEvents: 'none',
            background: 'linear-gradient(to right, transparent, rgba(22,27,34,0.95))',
            display: { xs: 'block', md: 'none' },
          }} />
        <Box sx={{
          display: 'flex', gap: 0.75, px: 2, py: 1.25, overflowX: 'auto',
          '::-webkit-scrollbar': { display: 'none' },
          scrollBehavior: 'smooth',
          WebkitOverflowScrolling: 'touch',
        }}>
          {CATEGORIES.map(({ id, label, icon: Icon }) => {
            const active = cat === id;
            return (
              <Box
                key={id}
                onClick={() => handleCatChange(id)}
                sx={{
                  display: 'flex', alignItems: 'center', gap: 0.75,
                  px: 1.5, py: 0.6, borderRadius: 2, cursor: 'pointer',
                  whiteSpace: 'nowrap', userSelect: 'none',
                  bgcolor: active ? 'primary.main' : 'rgba(255,255,255,0.05)',
                  color: active ? 'white' : 'text.secondary',
                  border: '1px solid',
                  borderColor: active ? 'primary.main' : 'rgba(255,255,255,0.12)',
                  transition: 'all 0.15s ease',
                  '&:hover': { bgcolor: active ? 'primary.dark' : 'rgba(255,255,255,0.09)' },
                }}
              >
                <Icon sx={{ fontSize: 15 }} />
                <Typography variant="body2" fontWeight={active ? 700 : 500} fontSize="0.78rem">{label}</Typography>
              </Box>
            );
          })}
        </Box>
        </Box>

        {/* Sub-tab row */}
        {currentCat && currentCat.subTabs.length > 1 && (
          <Tabs
            value={subTab}
            onChange={(_, v) => setSubTab(v)}
            variant="scrollable"
            scrollButtons="auto"
            allowScrollButtonsMobile
            sx={{ px: 2, minHeight: 38, '& .MuiTab-root': { minHeight: 38, py: 0 } }}
          >
            {currentCat.subTabs.map((label) => (
              <Tab key={label} label={label} sx={{ fontSize: '0.8rem' }} />
            ))}
          </Tabs>
        )}
      </AppBar>

      <Box sx={{
        maxWidth: 900, mx: 'auto', p: { xs: 2, md: 3 },
        // Clear the mobile bottom navigation bar + iPhone safe area so the last
        // controls aren't hidden behind it (shared token, matches AppLayout).
        pb: { xs: 'var(--bottom-nav-clearance)', md: 3 },
      }}>

        {/* ══════════════════════════════════════════════════════════
            MODERATION
        ══════════════════════════════════════════════════════════ */}

        {/* MODERATION › AutoMod */}
        {cat === 'moderation' && subTab === 0 && (
          <>
            <CollapsibleCard id="tg.moderation.automod" title="AutoMod">
                <FormControlLabel
                  control={<Switch checked={!!am.enabled} onChange={(e) => updateSetting('automod.enabled', e.target.checked)} />}
                  label="Enable AutoMod globally"
                />
                <Divider sx={{ my: 2 }} />
                <Typography variant="subtitle2" fontWeight={600} mb={1}>Core Rules</Typography>
                <Grid container spacing={1}>
                  {[
                    ['Spam Detection', 'automod.spam.enabled', !!(am.spam || {}).enabled],
                    ['Bad Words Filter', 'automod.bad_words.enabled', !!(am.bad_words || {}).enabled],
                    ['NSFW / Adult Filter', 'automod.nsfw_filter.enabled', !!(am.nsfw_filter || {}).enabled],
                    ['Scan Inline Buttons', 'automod.inline_button_scan.enabled', !!(am.inline_button_scan || {}).enabled],
                    ['Block External Links', 'automod.external_links.enabled', !!(am.external_links || {}).enabled],
                    ['Block Telegram Links', 'automod.telegram_links.enabled', !!(am.telegram_links || {}).enabled],
                    ['Excessive Emojis', 'automod.excessive_emojis.enabled', !!(am.excessive_emojis || {}).enabled],
                    ['Caps Lock Filter', 'automod.caps_lock.enabled', !!(am.caps_lock || {}).enabled],
                    ['Block Forwarded Messages', 'automod.forwarded_messages.enabled', !!(am.forwarded_messages || {}).enabled],
                    ['Homoglyph Normalization', 'automod.homoglyphs.enabled', !!(am.homoglyphs || {}).enabled],
                  ].map(([label, path, checked]) => (
                    <Grid item xs={12} sm={6} key={path}>
                      <FormControlLabel
                        control={<Switch checked={checked} onChange={(e) => updateSetting(path, e.target.checked)} />}
                        label={label}
                      />
                    </Grid>
                  ))}
                </Grid>
                <TextField fullWidth multiline rows={2} label="Banned Words (comma separated)" sx={{ mt: 2 }}
                  value={(am.bad_words?.words || []).join(', ')}
                  onChange={(e) => updateSetting('automod.bad_words.words', e.target.value.split(',').map(w => w.trim()).filter(Boolean))} />
                <BlockedWordPresets packs={TELEGRAM_PACKS} onAdd={(words) => {
                  const cur = am.bad_words?.words || [];
                  updateSetting('automod.bad_words.words', Array.from(new Set([...cur, ...words])));
                }} />
                <TextField fullWidth multiline rows={2} label="Extra NSFW Words (comma separated)" sx={{ mt: 2 }}
                  helperText="Added to the built-in adult/NSFW word list. Plain text is deleted + warned; NSFW on inline buttons is banned."
                  value={(am.nsfw_filter?.extra_words || []).join(', ')}
                  onChange={(e) => updateSetting('automod.nsfw_filter.extra_words', e.target.value.split(',').map(w => w.trim()).filter(Boolean))} />
            </CollapsibleCard>

            {/* Slow Mode — per-user minimum gap between messages (smart slow mode) */}
            <CollapsibleCard id="tg.moderation.slow_mode" title="🐢 Slow Mode">
                <Typography variant="body2" color="text.secondary" mb={2}>
                  Enforces a <b>minimum gap between each member's messages</b> — a smarter version
                  of Telegram's built-in slow mode. Unlike Spam Detection (which catches rapid
                  bursts), this keeps a steady pace. Admins and trusted users are always exempt,
                  and you can let high-level members skip it. Requires AutoMod to be enabled.
                </Typography>

                <Alert severity="info" icon={false} sx={{ mb: 2 }}>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                    <b>Want Telegram's native cooldown</b> (greyed-out box + live countdown that blocks
                    sending before it even happens)? Bots can't switch that on — only a human admin can,
                    in Telegram itself:
                  </Typography>
                  <Typography component="ol" variant="caption" color="text.secondary"
                    sx={{ pl: 2.5, m: 0, mt: 0.75, '& li': { mb: 0.25 } }}>
                    <li>Open your group and tap its <b>name/title</b> at the top to open Group Info.</li>
                    <li>Tap <b>Edit</b> (the pencil icon).</li>
                    <li>Open <b>Permissions</b> (the lock / key icon).</li>
                    <li>Scroll down to <b>Slow Mode</b> and pick an interval (5s – 1h).</li>
                    <li>Done — Telegram now shows every member a per-user "write again in …" timer.</li>
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
                    You can run both at once — they don't conflict. Telegram's timer stops the message
                    up front; our smart slow mode below adds per-level exemptions and harsher actions
                    (mute/warn) on top.
                  </Typography>
                </Alert>

                <FormControlLabel
                  control={<Switch checked={!!sm.enabled}
                    onChange={(e) => updateSetting('automod.slow_mode.enabled', e.target.checked)} />}
                  label="Enable slow mode"
                />

                <Grid container spacing={2} sx={{ mt: 0.5 }}>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth size="small" type="number"
                      label="Seconds between messages"
                      value={sm.seconds_between_messages ?? 60}
                      onChange={(e) => updateSetting('automod.slow_mode.seconds_between_messages', Math.max(5, parseInt(e.target.value || '0', 10)))}
                      helperText="Minimum wait after a member's previous message."
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth size="small" type="number"
                      label="Exempt members at level ≥"
                      value={sm.exempt_min_level ?? 0}
                      onChange={(e) => updateSetting('automod.slow_mode.exempt_min_level', Math.max(0, parseInt(e.target.value || '0', 10)))}
                      helperText="0 = no level exemption. Admins & trusted users always bypass."
                    />
                  </Grid>
                </Grid>

                <FormControl fullWidth size="small" sx={{ mt: 2 }}>
                  <InputLabel>Action on a too-fast message</InputLabel>
                  <Select
                    label="Action on a too-fast message"
                    value={sm.action || 'delete'}
                    onChange={(e) => updateSetting('automod.slow_mode.action', e.target.value)}
                  >
                    <MenuItem value="delete">Delete silently (recommended)</MenuItem>
                    <MenuItem value="warn">Delete + warn (notice throttled to once per gap)</MenuItem>
                    <MenuItem value="restrict">Cooldown — restrict until next allowed message + notice</MenuItem>
                    <MenuItem value="mute">Mute the member temporarily</MenuItem>
                  </Select>
                </FormControl>

                {sm.action === 'restrict' && (
                  <>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                      Removes the too-fast message and restricts the member <b>only until their next
                      allowed time</b> (the remaining gap) — Telegram then shows them an auto-lifting
                      "you can write again in …" countdown. This is the closest thing to Telegram's
                      native per-user timer (which bots can't set). Admins are never affected.
                    </Typography>
                    <FormControlLabel sx={{ mt: 1 }}
                      control={<Switch checked={sm.notify !== false}
                        onChange={(e) => updateSetting('automod.slow_mode.notify', e.target.checked)} />}
                      label="Post a short, self-deleting “please wait Ns” notice"
                    />
                  </>
                )}

                {sm.action === 'warn' && (
                  <FormControlLabel sx={{ mt: 1 }}
                    control={<Switch checked={sm.notify !== false}
                      onChange={(e) => updateSetting('automod.slow_mode.notify', e.target.checked)} />}
                    label="Post the warning notice (off = silent delete)"
                  />
                )}

                {sm.action === 'mute' && (
                  <TextField
                    fullWidth size="small" type="number" sx={{ mt: 2 }}
                    label="Mute duration (minutes)"
                    value={sm.mute_duration_minutes ?? 5}
                    onChange={(e) => updateSetting('automod.slow_mode.mute_duration_minutes', Math.max(1, parseInt(e.target.value || '0', 10)))}
                  />
                )}
            </CollapsibleCard>

            {/* Bot Protection — controls bots added to the group (Phase 1) */}
            <CollapsibleCard id="tg.moderation.bot_protection" title="🛡️ Bot Protection">
                <Typography variant="body2" color="text.secondary" mb={2}>
                  Telegram never delivers another bot's <i>messages</i> to us, so bot spam
                  (adult content, link-farm buttons, scam bots) can only be stopped when the
                  bot <b>joins</b>. New bots are muted instantly and held for your approval —
                  no spam reaches the group while you decide.
                </Typography>

                <FormControlLabel
                  control={<Switch checked={bp.enabled !== false}
                    onChange={(e) => updateSetting('bot_policy.enabled', e.target.checked)} />}
                  label="Enable bot protection"
                />

                <FormControl fullWidth size="small" sx={{ mt: 2 }}>
                  <InputLabel>Bot policy</InputLabel>
                  <Select
                    label="Bot policy"
                    value={bp.policy || 'restrict_until_approval'}
                    onChange={(e) => updateSetting('bot_policy.policy', e.target.value)}
                  >
                    <MenuItem value="allow_all">Allow all bots (no protection)</MenuItem>
                    <MenuItem value="restrict_until_approval">Restrict new bots until admin approval</MenuItem>
                    <MenuItem value="block_unapproved">Block all non-trusted bots (auto-ban)</MenuItem>
                    <MenuItem value="allowlist_only">Allow only trusted bots</MenuItem>
                  </Select>
                </FormControl>

                <Grid container spacing={2} sx={{ mt: 0.5 }}>
                  <Grid item xs={12} sm={6}>
                    <FormControl fullWidth size="small">
                      <InputLabel>Notify admins via</InputLabel>
                      <Select
                        label="Notify admins via"
                        value={bp.notify || 'dm'}
                        onChange={(e) => updateSetting('bot_policy.notify', e.target.value)}
                      >
                        <MenuItem value="dm">Private DM (recommended)</MenuItem>
                        <MenuItem value="group">In group (linkless)</MenuItem>
                        <MenuItem value="both">DM + group</MenuItem>
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <FormControl fullWidth size="small">
                      <InputLabel>If no admin decides</InputLabel>
                      <Select
                        label="If no admin decides"
                        value={bp.on_timeout || 'ban'}
                        onChange={(e) => updateSetting('bot_policy.on_timeout', e.target.value)}
                      >
                        <MenuItem value="ban">Auto-ban the bot</MenuItem>
                        <MenuItem value="keep_restricted">Keep it muted</MenuItem>
                      </Select>
                    </FormControl>
                  </Grid>
                </Grid>

                <TextField
                  fullWidth size="small" type="number" sx={{ mt: 2 }}
                  label="Approval timeout (minutes)"
                  value={bp.approval_timeout_minutes ?? 60}
                  onChange={(e) => updateSetting('bot_policy.approval_timeout_minutes', Math.max(0, parseInt(e.target.value || '0', 10)))}
                  helperText="The bot stays muted the whole time. 0 disables the timer (stays muted until you act)."
                />

                <FormControlLabel sx={{ mt: 1 }}
                  control={<Switch checked={bp.auto_trust_own_bots !== false}
                    onChange={(e) => updateSetting('bot_policy.auto_trust_own_bots', e.target.checked)} />}
                  label="Auto-trust the Telegizer bot and your own custom bots"
                />

                <Divider sx={{ my: 2 }} />
                <Typography variant="subtitle2" fontWeight={600} mb={1}>Trusted bots</Typography>
                <Typography variant="body2" color="text.secondary" mb={1}>
                  These bots are never restricted. Approving a bot from an alert adds it here automatically.
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 1 }}>
                  {(bp.trusted_bot_usernames || []).length === 0 && (
                    <Typography variant="body2" color="text.disabled">No bots added yet.</Typography>
                  )}
                  {(bp.trusted_bot_usernames || []).map((u) => (
                    <Chip key={u} label={'@' + u} onDelete={() => {
                      const next = (bp.trusted_bot_usernames || []).filter((x) => x !== u);
                      updateSetting('bot_policy.trusted_bot_usernames', next);
                    }} />
                  ))}
                </Box>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <TextField
                    fullWidth size="small" placeholder="username (without @)"
                    value={trustedBotInput}
                    onChange={(e) => setTrustedBotInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTrustedBot(); } }}
                  />
                  <Button variant="outlined" onClick={addTrustedBot}>Add</Button>
                </Box>
            </CollapsibleCard>

            {/* Raid Mode — behaviour-based coordinated-spam lockdown (Phase 3) */}
            <CollapsibleCard id="tg.moderation.raid_mode" title="🚨 Raid Mode">
                <Typography variant="body2" color="text.secondary" mb={2}>
                  Detects <b>coordinated</b> spam — many different accounts tripping the
                  filters, or posting the same message, in a short burst. It does <b>not</b>
                  lock on join rate (healthy spikes like shout-outs are fine). When a raid is
                  detected, the bot temporarily restricts <i>messaging</i> (not joining) until
                  it settles — choose who gets muted below.
                </Typography>

                <FormControlLabel
                  control={<Switch checked={!!rg.enabled}
                    onChange={(e) => updateSetting('raid_guard.enabled', e.target.checked)} />}
                  label="Enable raid mode"
                />

                <Grid container spacing={2} sx={{ mt: 0.5 }}>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth size="small" type="number"
                      label="Distinct spammers to trigger"
                      value={rg.trigger_violators ?? 5}
                      onChange={(e) => updateSetting('raid_guard.trigger_violators', Math.max(2, parseInt(e.target.value || '0', 10)))}
                      helperText="Different users tripping the filters within the window."
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth size="small" type="number"
                      label="Duplicate posters to trigger"
                      value={rg.duplicate_threshold ?? 5}
                      onChange={(e) => updateSetting('raid_guard.duplicate_threshold', Math.max(2, parseInt(e.target.value || '0', 10)))}
                      helperText="Different users posting the same message in the window."
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth size="small" type="number"
                      label="Detection window (seconds)"
                      value={rg.window_seconds ?? 60}
                      onChange={(e) => updateSetting('raid_guard.window_seconds', Math.max(5, parseInt(e.target.value || '0', 10)))}
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth size="small" type="number"
                      label="Lockdown duration (minutes)"
                      value={rg.lockdown_minutes ?? 10}
                      onChange={(e) => updateSetting('raid_guard.lockdown_minutes', Math.max(1, parseInt(e.target.value || '0', 10)))}
                    />
                  </Grid>
                </Grid>

                <FormControl fullWidth size="small" sx={{ mt: 2 }}>
                  <InputLabel>Who gets muted during a raid</InputLabel>
                  <Select
                    label="Who gets muted during a raid"
                    value={rg.lockdown_scope || 'recent_joiners'}
                    onChange={(e) => updateSetting('raid_guard.lockdown_scope', e.target.value)}
                  >
                    <MenuItem value="recent_joiners">Only new / recent joiners (recommended)</MenuItem>
                    <MenuItem value="all">Everyone except admins (group goes read-only)</MenuItem>
                  </Select>
                </FormControl>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                  “Everyone except admins” temporarily mutes any non-admin who posts while the
                  raid is active — messaging is restricted, members are never blocked from joining.
                </Typography>

                <FormControl fullWidth size="small" sx={{ mt: 2 }}>
                  <InputLabel>Action on members who join during a raid</InputLabel>
                  <Select
                    label="Action on members who join during a raid"
                    value={rg.lockdown_action || 'mute'}
                    onChange={(e) => updateSetting('raid_guard.lockdown_action', e.target.value)}
                  >
                    <MenuItem value="mute">Mute (recommended — reversible)</MenuItem>
                    <MenuItem value="kick">Kick (they can rejoin after the raid)</MenuItem>
                  </Select>
                </FormControl>

                <FormControlLabel sx={{ mt: 1 }}
                  control={<Switch checked={rg.notify !== false}
                    onChange={(e) => updateSetting('raid_guard.notify', e.target.checked)} />}
                  label="Post an in-group alert when raid mode activates"
                />

                {rg.notify !== false && (
                  <TextField
                    sx={{ mt: 1, maxWidth: 360 }}
                    fullWidth size="small" type="number"
                    label="Auto-delete the alert after (seconds)"
                    value={rg.notice_auto_delete_seconds ?? 0}
                    onChange={(e) => updateSetting('raid_guard.notice_auto_delete_seconds', Math.max(0, parseInt(e.target.value || '0', 10)))}
                    helperText="0 = keep the alert in the chat. e.g. 30 or 60 removes it after that many seconds."
                  />
                )}

                <Divider sx={{ my: 2 }} />
                <Typography variant="subtitle2" fontWeight={600} mb={1}>Emergency lockdown</Typography>
                {(() => {
                  const until = rg.manual_lockdown_until ? new Date(rg.manual_lockdown_until) : null;
                  const active = until && until.getTime() > Date.now();
                  if (active) {
                    return (
                      <Alert severity="warning" sx={{ alignItems: 'center' }}
                        action={<Button color="inherit" size="small" disabled={saving}
                          onClick={() => setEmergencyLockdown(null)}>Lift now</Button>}>
                        Locked down until <b>{fmtTs(rg.manual_lockdown_until)}</b> — every new
                        member is being auto-{rg.lockdown_action || 'mute'}d on join.
                      </Alert>
                    );
                  }
                  return (
                    <Box>
                      <Typography variant="body2" color="text.secondary" mb={1}>
                        Instantly restrict <b>all</b> new joiners for a set time — use during an
                        active attack. Works even if raid detection above is off.
                      </Typography>
                      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
                        <FormControl size="small" sx={{ minWidth: 130 }}>
                          <InputLabel>Duration</InputLabel>
                          <Select label="Duration" value={emergencyMins}
                            onChange={(e) => setEmergencyMins(e.target.value)}>
                            <MenuItem value={15}>15 minutes</MenuItem>
                            <MenuItem value={60}>1 hour</MenuItem>
                            <MenuItem value={360}>6 hours</MenuItem>
                            <MenuItem value={1440}>24 hours</MenuItem>
                          </Select>
                        </FormControl>
                        <Button variant="contained" color="error" disabled={saving}
                          onClick={() => setEmergencyLockdown(emergencyMins)}>
                          Activate emergency lockdown
                        </Button>
                      </Box>
                    </Box>
                  );
                })()}
            </CollapsibleCard>

            {/* Smart Moderation — 3-layer AI-powered system (Pro only) */}
            <CollapsibleCard
              id="tg.moderation.smart_moderation"
              title="Smart Moderation"
              badge={<>
                  <Chip
                    label={(am.smart_mod || {}).ai_enabled ? 'AI Active' : 'Rule-based · AI optional'}
                    size="small"
                    color={(am.smart_mod || {}).ai_enabled ? 'primary' : 'default'}
                    variant="outlined"
                  />
                  <ProBadge />
              </>}
            >
                <Typography variant="body2" color="text.secondary" mb={2}>
                  Three-layer system: fast rules → hidden URL detection → optional AI relevance check.
                  The AI layer runs <b>only</b> when you enable Layer 3 below <b>and</b> a workspace AI key
                  is set (Settings → AI). Without a key, moderation stays rule-based.
                </Typography>
                {/* Trusted bots & channels — exempt from ALL moderation. Not Pro-gated:
                    this protects core Telegram features (e.g. a linked channel's posts
                    that open the comment section) for everyone. */}
                <Box sx={{ p: 2, mb: 2, bgcolor: 'rgba(255,255,255,0.03)', border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
                  <Typography variant="subtitle2" fontWeight={600} mb={0.5}>
                    🔓 Trusted bots &amp; channels
                  </Typography>
                  <Typography variant="body2" color="text.secondary" mb={1.5}>
                    Messages from these are <b>never</b> moderated. Your <b>linked channel</b> (the
                    posts that open each comment thread) and <b>anonymous admins</b> are exempt
                    automatically — add anything extra here, like other management bots or a
                    cross-posting channel. Use an @username or a numeric ID.
                  </Typography>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 1 }}>
                    {((am.allowlist) || []).length === 0 && (
                      <Typography variant="body2" color="text.disabled">
                        Nothing added — your linked channel is still protected automatically.
                      </Typography>
                    )}
                    {((am.allowlist) || []).map((u) => (
                      <Chip key={u} label={/^-?\d+$/.test(u) ? u : '@' + u} onDelete={() => {
                        const next = ((am.allowlist) || []).filter((x) => x !== u);
                        updateSetting('automod.allowlist', next);
                      }} />
                    ))}
                  </Box>
                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <TextField
                      fullWidth size="small" placeholder="@username or numeric ID"
                      value={allowlistInput}
                      onChange={(e) => setAllowlistInput(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addAllowlistEntry(); } }}
                    />
                    <Button variant="outlined" onClick={addAllowlistEntry}>Add</Button>
                  </Box>
                </Box>

                <PlanGate plan="pro" userTier={userTier} feature="Smart Moderation">
                <FormControlLabel
                  control={<Switch checked={!!(am.smart_mod || {}).enabled}
                    onChange={(e) => updateSetting('automod.smart_mod.enabled', e.target.checked)} />}
                  label="Enable Smart Moderation"
                />

                <TextField
                  fullWidth
                  label="Group Topic"
                  placeholder="e.g. CreatorX — creator economy tools and discussion"
                  value={(am.smart_mod || {}).group_topic || ''}
                  onChange={(e) => updateSetting('automod.smart_mod.group_topic', e.target.value)}
                  sx={{ mt: 2 }}
                  helperText="Describe what this group is about. Used by Layer 3 AI to judge relevance."
                />

                <Divider sx={{ my: 2 }} />
                <Typography variant="subtitle2" fontWeight={600} mb={1}>Layer 2 — Pattern Detection</Typography>
                <Grid container spacing={1}>
                  <Grid item xs={12} sm={6}>
                    <FormControlLabel
                      control={<Switch checked={!!(am.smart_mod || {}).promotional_detection}
                        onChange={(e) => updateSetting('automod.smart_mod.promotional_detection', e.target.checked)} />}
                      label="Detect promotional content"
                    />
                    <Typography variant="caption" color="text.secondary" display="block" ml={4}>
                      Ads, DM spam, referral codes, fake earnings, crypto shilling
                    </Typography>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <FormControlLabel
                      control={<Switch checked={!!(am.smart_mod || {}).hidden_url_detection}
                        onChange={(e) => updateSetting('automod.smart_mod.hidden_url_detection', e.target.checked)} />}
                      label="Detect hidden/obfuscated URLs"
                    />
                    <Typography variant="caption" color="text.secondary" display="block" ml={4}>
                      t_me/x, site dot com, hxxps://, example_com, etc.
                    </Typography>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <FormControlLabel
                      control={<Switch checked={!!(am.smart_mod || {}).allow_referral_codes}
                        onChange={(e) => updateSetting('automod.smart_mod.allow_referral_codes', e.target.checked)} />}
                      label="Allow referral codes"
                    />
                    <Typography variant="caption" color="text.secondary" display="block" ml={4}>
                      Whitelists messages that mention a referral/affiliate code so they aren't auto-removed
                      as promotion (e.g. “use my code WELCOME10”). Leave off to treat referral codes as spam.
                    </Typography>
                  </Grid>
                </Grid>

                <Divider sx={{ my: 2 }} />
                <Typography variant="subtitle2" fontWeight={600} mb={1}>Layer 3 — AI Relevance Check</Typography>
                <FormControlLabel
                  control={<Switch checked={!!(am.smart_mod || {}).ai_enabled}
                    onChange={(e) => updateSetting('automod.smart_mod.ai_enabled', e.target.checked)} />}
                  label="Enable AI check for off-topic and unclear messages"
                />
                <Typography variant="caption" color="text.secondary" display="block" ml={4} mb={1}>
                  Uses your workspace AI key. Only runs when Layers 1 & 2 pass. Skips messages under 10 words.
                </Typography>

                <Divider sx={{ my: 2 }} />
                <Typography variant="subtitle2" fontWeight={600} mb={1}>Action & Whitelist</Typography>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
                  <FormControl size="small" sx={{ minWidth: 140 }}>
                    <InputLabel>Action</InputLabel>
                    <Select
                      value={(am.smart_mod || {}).action || 'delete'}
                      label="Action"
                      onChange={(e) => updateSetting('automod.smart_mod.action', e.target.value)}
                    >
                      <MenuItem value="delete">Delete</MenuItem>
                      <MenuItem value="warn">Warn</MenuItem>
                      <MenuItem value="mute">Mute</MenuItem>
                    </Select>
                  </FormControl>
                  <FormControlLabel
                    control={<Switch checked={!!(am.smart_mod || {}).warn_user}
                      onChange={(e) => updateSetting('automod.smart_mod.warn_user', e.target.checked)} />}
                    label="Warn user"
                  />
                </Box>
                <Box sx={{ mt: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="subtitle2" fontWeight={600}>Group Admins</Typography>
                    <Tooltip title="Refresh admin list">
                      <IconButton size="small" onClick={fetchAdmins} disabled={adminsLoading}>
                        {adminsLoading ? <CircularProgress size={16} /> : <Refresh fontSize="small" />}
                      </IconButton>
                    </Tooltip>
                  </Box>
                  <Typography variant="caption" color="text.secondary" display="block" mb={1.5}>
                    Toggle trusted bypass ON for admins whose messages should skip all smart moderation checks.
                  </Typography>
                  {groupAdmins.length === 0 ? (
                    <Alert severity="info" icon={false} sx={{ mb: 1 }}>
                      <Typography variant="caption">
                        Click Refresh to load group admins. Admins must be registered in the bot.
                      </Typography>
                    </Alert>
                  ) : (
                    <Stack spacing={1}>
                      {groupAdmins.map((admin) => {
                        const trusted = ((am.smart_mod || {}).trusted_users || []).includes(admin.user_id);
                        return (
                          <Box key={admin.user_id} sx={{
                            display: 'flex', alignItems: 'center', gap: 1.5,
                            p: 1, border: '1px solid', borderRadius: 1.5,
                            borderColor: trusted ? 'success.main' : 'divider',
                            bgcolor: trusted ? 'rgba(76,175,80,0.04)' : 'transparent',
                          }}>
                            <Avatar sx={{ width: 32, height: 32, fontSize: '0.85rem', bgcolor: 'primary.main' }}>
                              {(admin.first_name || '?')[0].toUpperCase()}
                            </Avatar>
                            <Box sx={{ flexGrow: 1 }}>
                              <Typography variant="body2" fontWeight={500}>
                                {admin.first_name}{admin.username ? ` (@${admin.username})` : ''}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {admin.status === 'creator' ? 'Owner' : 'Admin'}
                              </Typography>
                            </Box>
                            {admin.can_dm ? (
                              <Chip label="✅ Started bot" color="success" size="small" variant="outlined" />
                            ) : (
                              <Tooltip title="Ask this admin to start @telegizer_bot first.">
                                <Chip label="⚠️ Not started" color="warning" size="small" variant="outlined" />
                              </Tooltip>
                            )}
                            <Switch
                              size="small"
                              checked={trusted}
                              onChange={(e) => {
                                const cur = ((am.smart_mod || {}).trusted_users || []);
                                const updated = e.target.checked
                                  ? [...new Set([...cur, admin.user_id])]
                                  : cur.filter(id => id !== admin.user_id);
                                updateSetting('automod.smart_mod.trusted_users', updated);
                              }}
                            />
                          </Box>
                        );
                      })}
                    </Stack>
                  )}
                </Box>
                </PlanGate>
            </CollapsibleCard>

            <CollapsibleCard
              id="tg.moderation.automod.extended_rules"
              title="Extended Rules — Media & Content"
              badge={<ProBadge />}
            >
                {/* Global defaults — apply once, inherited by all enabled rules */}
                <Box sx={{ p: 2, mb: 2, bgcolor: 'rgba(255,255,255,0.03)', border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
                  <Typography variant="subtitle2" fontWeight={700} mb={1.5}>Default settings for all rules</Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
                    <FormControl size="small" sx={{ minWidth: 130 }}>
                      <InputLabel>Default action</InputLabel>
                      <Select
                        value={am.ext_default_action || 'delete'}
                        label="Default action"
                        onChange={(e) => updateSetting('automod.ext_default_action', e.target.value)}
                      >
                        <MenuItem value="delete">Delete</MenuItem>
                        <MenuItem value="warn">Warn</MenuItem>
                        <MenuItem value="mute">Mute</MenuItem>
                        <MenuItem value="ban">Ban</MenuItem>
                      </Select>
                    </FormControl>
                    <FormControlLabel
                      control={<Switch
                        checked={!!am.ext_default_warn_user}
                        onChange={(e) => updateSetting('automod.ext_default_warn_user', e.target.checked)}
                      />}
                      label="Warn user"
                    />
                    {am.ext_default_warn_user && (
                      <FormControl size="small" sx={{ minWidth: 170 }}>
                        <InputLabel>Delete warning after</InputLabel>
                        <Select
                          value={am.ext_default_warn_delete_seconds ?? 0}
                          label="Delete warning after"
                          onChange={(e) => updateSetting('automod.ext_default_warn_delete_seconds', e.target.value)}
                        >
                          <MenuItem value={0}>Never</MenuItem>
                          <MenuItem value={5}>5 seconds</MenuItem>
                          <MenuItem value={10}>10 seconds</MenuItem>
                          <MenuItem value={30}>30 seconds</MenuItem>
                          <MenuItem value={60}>1 minute</MenuItem>
                          <MenuItem value={300}>5 minutes</MenuItem>
                        </Select>
                      </FormControl>
                    )}
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => {
                        const defaultAction = am.ext_default_action || 'delete';
                        const defaultWarn = !!am.ext_default_warn_user;
                        const defaultExpiry = am.ext_default_warn_delete_seconds ?? 0;
                        AUTOMOD_EXTENDED_RULES.forEach(({ key }) => {
                          const rule = am[key] || {};
                          if (rule.enabled) {
                            updateSetting(`automod.${key}.action`, defaultAction);
                            updateSetting(`automod.${key}.warn_user`, defaultWarn);
                            updateSetting(`automod.${key}.warn_delete_seconds`, defaultExpiry);
                          }
                        });
                      }}
                    >
                      Apply to all enabled rules
                    </Button>
                  </Box>
                  <Typography variant="caption" color="text.secondary" display="block" mt={1}>
                    Click "Apply" to push these defaults to every currently-enabled rule below. Individual rules can still be overridden.
                  </Typography>
                </Box>

                <Grid container spacing={1}>
                  {AUTOMOD_EXTENDED_RULES.map(({ key, label }) => {
                    const rule = am[key] || {};
                    return (
                      <Grid item xs={12} key={key}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap', py: 0.5 }}>
                          <FormControlLabel
                            sx={{ minWidth: 280 }}
                            control={<Switch checked={!!rule.enabled}
                              onChange={(e) => updateSetting(`automod.${key}.enabled`, e.target.checked)} />}
                            label={label}
                          />
                          {rule.enabled && (
                            <>
                              <FormControl size="small" sx={{ minWidth: 120 }}>
                                <InputLabel>Action</InputLabel>
                                <Select value={rule.action || 'delete'} label="Action"
                                  onChange={(e) => updateSetting(`automod.${key}.action`, e.target.value)}>
                                  <MenuItem value="delete">Delete</MenuItem>
                                  <MenuItem value="warn">Warn</MenuItem>
                                  <MenuItem value="mute">Mute</MenuItem>
                                  <MenuItem value="ban">Ban</MenuItem>
                                </Select>
                              </FormControl>
                              <FormControlLabel
                                control={<Switch checked={!!rule.warn_user}
                                  onChange={(e) => updateSetting(`automod.${key}.warn_user`, e.target.checked)} />}
                                label="Warn user"
                              />
                            </>
                          )}
                        </Box>
                      </Grid>
                    );
                  })}
                </Grid>
            </CollapsibleCard>

            <CollapsibleCard
              id="tg.moderation.automod.language_filter"
              title="Language Filter"
              badge={<ProBadge />}
            >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2, flexWrap: 'wrap' }}>
                  <FormControlLabel
                    control={<Switch checked={!!(am.language_filter || {}).enabled}
                      onChange={(e) => updateSetting('automod.language_filter.enabled', e.target.checked)} />}
                    label="Enable language filter"
                  />
                  <FormControl size="small" sx={{ minWidth: 120 }}>
                    <InputLabel>Action</InputLabel>
                    <Select value={(am.language_filter || {}).action || 'delete'} label="Action"
                      onChange={(e) => updateSetting('automod.language_filter.action', e.target.value)}>
                      <MenuItem value="delete">Delete</MenuItem>
                      <MenuItem value="warn">Warn</MenuItem>
                      <MenuItem value="mute">Mute</MenuItem>
                    </Select>
                  </FormControl>
                </Box>
                <Typography variant="body2" color="text.secondary" mb={1}>Block messages containing these scripts:</Typography>
                <Grid container spacing={1}>
                  {LANGUAGE_OPTIONS.map(({ value, label }) => {
                    const langs = (am.language_filter || {}).languages || [];
                    const checked = langs.includes(value);
                    return (
                      <Grid item xs={12} sm={6} key={value}>
                        <FormControlLabel
                          control={<Switch checked={checked} onChange={(e) => {
                            const newLangs = e.target.checked ? [...langs, value] : langs.filter(l => l !== value);
                            updateSetting('automod.language_filter.languages', newLangs);
                          }} />}
                          label={label}
                        />
                      </Grid>
                    );
                  })}
                </Grid>
            </CollapsibleCard>

            {/* Emoji Reactions */}
            <CollapsibleCard id="tg.moderation.automod.emoji_reactions" title="Emoji Reactions">
                <Typography variant="body2" color="text.secondary" mb={2}>
                  React to messages with emojis based on their sentiment. Admin messages always get 👍. Member messages get ❤️ 🔥 😂 👍 🎉 🫂 based on tone.
                </Typography>
                <FormControlLabel
                  control={<Switch checked={!!(settingsData.reactions || {}).enabled}
                    onChange={(e) => updateSetting('reactions.enabled', e.target.checked)} />}
                  label="Enable emoji reactions"
                />
                <Box sx={{ mt: 1, display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                  <FormControlLabel
                    control={<Switch checked={(settingsData.reactions || {}).admin_thumbs_up !== false}
                      onChange={(e) => updateSetting('reactions.admin_thumbs_up', e.target.checked)} />}
                    label="👍 Thumbs up on every admin message"
                  />
                  <FormControlLabel
                    control={<Switch checked={(settingsData.reactions || {}).sentiment_reactions !== false}
                      onChange={(e) => updateSetting('reactions.sentiment_reactions', e.target.checked)} />}
                    label="React to member messages based on sentiment (❤️ 🔥 😂 👍 🎉 🫂)"
                  />
                </Box>
            </CollapsibleCard>

            <CollapsibleCard id="tg.moderation.command_permissions" title="Command Permissions">
                <Typography variant="body2" color="text.secondary" mb={2}>
                  Control who can use moderation commands. Default is admins only.
                </Typography>
                <FormControlLabel
                  sx={{ mb: 1 }}
                  control={<Switch
                    checked={am.delete_unauthorized_commands !== false}
                    onChange={(e) => updateSetting('automod.delete_unauthorized_commands', e.target.checked)} />}
                  label="Delete unauthorized command messages"
                />
                <Typography variant="caption" color="text.secondary" display="block" mb={2}>
                  When a non-admin uses an admin-only command, delete their message instead of replying in the
                  group. The attempt is still recorded in the audit log; the user is never DM'd unless they
                  have already started the bot.
                </Typography>
                <Box sx={{ maxWidth: 460 }}>
                {['/warn', '/ban', '/mute', '/kick'].map((cmd) => {
                  const key = cmd.slice(1);
                  const val = (am.cmd_perms || {})[key] || 'admins_only';
                  return (
                    <Box key={cmd} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2, py: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}>
                      <Typography fontWeight={600} sx={{ fontFamily: 'monospace', fontSize: '0.9rem', minWidth: 70 }}>{cmd}</Typography>
                      <FormControl size="small" sx={{ minWidth: 160 }}>
                        <Select
                          value={val}
                          onChange={(e) => updateSetting(`automod.cmd_perms.${key}`, e.target.value)}
                        >
                          <MenuItem value="admins_only">Admins only</MenuItem>
                          <MenuItem value="everyone">Everyone</MenuItem>
                        </Select>
                      </FormControl>
                    </Box>
                  );
                })}
                </Box>
            </CollapsibleCard>

            {/* Protection Activity — bot-policy + raid-mode event log (Phase 4).
                Lives at the very bottom of AutoMod and is collapsible. */}
            <CollapsibleCard
              id="tg.moderation.protection_activity"
              title="📋 Protection Activity"
              action={
                <Button size="small" onClick={fetchProtectionLog} disabled={protectionLoading}>
                  {protectionLoading ? 'Refreshing…' : 'Refresh'}
                </Button>
              }
            >
              <Typography variant="body2" color="text.secondary" mb={2}>
                What the bot did at <b>join time</b> — restricting/banning new bots and
                locking down raids. These never appear in the normal moderation log.
              </Typography>
              {protectionLog.length === 0 ? (
                <Typography variant="body2" color="text.disabled">
                  {protectionLoading ? 'Loading…' : 'No protection events yet.'}
                </Typography>
              ) : (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                  {protectionLog.map((ev) => {
                    const meta = ev.metadata || {};
                    const info = PROTECTION_EVENT_META[ev.event_type] || { icon: '•', label: ev.event_type };
                    const who = meta.target_username
                      ? '@' + String(meta.target_username).replace(/^@/, '')
                      : (meta.target_user_id ? `id ${meta.target_user_id}` : '');
                    return (
                      <Box key={ev.id} sx={{ display: 'flex', alignItems: 'flex-start', gap: 1,
                        py: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}>
                        <Typography component="span" sx={{ fontSize: 18, lineHeight: 1.4 }}>{info.icon}</Typography>
                        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                          <Typography variant="body2" fontWeight={600}>
                            {info.label}{who ? ` — ${who}` : ''}
                          </Typography>
                          {(ev.message || meta.reason) && (
                            <Typography variant="caption" color="text.secondary"
                              sx={{ display: 'block', wordBreak: 'break-word' }}>
                              {ev.message || meta.reason}
                            </Typography>
                          )}
                        </Box>
                        <Typography variant="caption" color="text.disabled" sx={{ whiteSpace: 'nowrap' }}>
                          {fmtTs(ev.created_at)}
                        </Typography>
                      </Box>
                    );
                  })}
                </Box>
              )}
            </CollapsibleCard>
          </>
        )}

        {/* MODERATION › Behavior */}
        {cat === 'moderation' && subTab === 1 && (
          <>
            <CollapsibleCard id="tg.moderation.warning_thresholds" title="Warning Thresholds">
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={4}>
                    <TextField fullWidth type="number" label="Max Warnings"
                      value={mod.max_warnings || 3}
                      helperText="Action below triggers once a user reaches this many warnings."
                      onChange={(e) => updateSetting('moderation.max_warnings', parseInt(e.target.value))} />
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <FormControl fullWidth>
                      <InputLabel>Warning Action</InputLabel>
                      <Select value={mod.warning_action || 'ban'} label="Warning Action"
                        onChange={(e) => updateSetting('moderation.warning_action', e.target.value)}>
                        <MenuItem value="ban">Ban</MenuItem>
                        <MenuItem value="kick">Kick</MenuItem>
                        <MenuItem value="mute">Mute</MenuItem>
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    {/* #2 — duration only applies to Mute. Ban is permanent; Kick has no duration. */}
                    {(mod.warning_action || 'ban') === 'mute' ? (
                      <TextField fullWidth type="number" label="Mute Duration (minutes)"
                        value={mod.mute_duration_minutes || 60}
                        onChange={(e) => updateSetting('moderation.mute_duration_minutes', parseInt(e.target.value))} />
                    ) : (
                      <TextField fullWidth disabled
                        label={(mod.warning_action || 'ban') === 'ban' ? 'Ban' : 'Kick'}
                        value={(mod.warning_action || 'ban') === 'ban'
                          ? 'Permanent — no duration'
                          : 'No duration — user can rejoin'}
                        helperText="Use the Escalation Chain below for a temporary ban with a set duration." />
                    )}
                  </Grid>
                </Grid>
            </CollapsibleCard>

            {/* Warning Escalation foundation — configurable but NOT enforced yet.
                Disabled by default; the owner finalises the rules before it goes live. */}
            <CollapsibleCard
              id="tg.moderation.warning_escalation"
              title="Warning Escalation"
              badge={we.enabled
                ? <Chip label="Active" size="small" color="success" variant="outlined" />
                : <Chip label="Off" size="small" color="default" variant="outlined" />}
            >
                <Typography variant="body2" color="text.secondary" mb={2}>
                  Automatically takes an action once a member reaches a warning threshold within a time window.
                  When enabled, this runs live on every warning the bot issues — admins and trusted users are
                  always exempt. Independent of the 3-strike ladder in Warning Thresholds.
                </Typography>
                <FormControlLabel
                  sx={{ mb: 1 }}
                  control={<Switch
                    checked={!!we.enabled}
                    onChange={(e) => updateSetting('warning_escalation.enabled', e.target.checked)} />}
                  label={we.enabled ? 'Enabled — rules are enforced' : 'Disabled — rules saved for later'}
                />
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={3}>
                    <TextField fullWidth type="number" label="Warning threshold"
                      value={we.warning_threshold ?? 3}
                      helperText="Warnings before action"
                      onChange={(e) => updateSetting('warning_escalation.warning_threshold', parseInt(e.target.value))} />
                  </Grid>
                  <Grid item xs={12} sm={3}>
                    <TextField fullWidth type="number" label="Time window (hours)"
                      value={we.time_window_hours ?? 24}
                      helperText="Blank = all-time"
                      onChange={(e) => {
                        const v = e.target.value;
                        updateSetting('warning_escalation.time_window_hours', v === '' ? null : parseInt(v));
                      }} />
                  </Grid>
                  <Grid item xs={12} sm={3}>
                    <FormControl fullWidth>
                      <InputLabel>Action</InputLabel>
                      <Select value={we.action_type || 'mute'} label="Action"
                        onChange={(e) => updateSetting('warning_escalation.action_type', e.target.value)}>
                        <MenuItem value="none">None</MenuItem>
                        <MenuItem value="mute">Mute</MenuItem>
                        <MenuItem value="kick">Kick</MenuItem>
                        <MenuItem value="ban">Ban</MenuItem>
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid item xs={12} sm={3}>
                    <TextField fullWidth type="number" label="Mute duration (minutes)"
                      disabled={(we.action_type || 'mute') !== 'mute'}
                      value={we.mute_duration_minutes ?? 60}
                      helperText={(we.action_type || 'mute') === 'mute' ? 'Used for Mute' : 'Mute only'}
                      onChange={(e) => updateSetting('warning_escalation.mute_duration_minutes', parseInt(e.target.value))} />
                  </Grid>
                </Grid>
            </CollapsibleCard>

            {/* #10 — auto-delete warning/action notices from the group chat */}
            <CollapsibleCard id="tg.moderation.warning_messages" title="Warning Messages">
                <Typography variant="body2" color="text.secondary" mb={2}>
                  Keep the chat clean by auto-removing the bot's warning notices. The warning is always kept
                  in the audit log even when the chat message is deleted.
                </Typography>
                <FormControlLabel
                  control={<Switch
                    checked={mod.auto_delete_warnings !== false}
                    onChange={(e) => updateSetting('moderation.auto_delete_warnings', e.target.checked)} />}
                  label="Auto-delete warning messages"
                />
                {mod.auto_delete_warnings !== false && (
                  <Box sx={{ mt: 2, maxWidth: 240 }}>
                    <FormControl fullWidth size="small">
                      <InputLabel>Delete after</InputLabel>
                      <Select
                        value={mod.auto_delete_warn_seconds || 30}
                        label="Delete after"
                        onChange={(e) => updateSetting('moderation.auto_delete_warn_seconds', parseInt(e.target.value))}
                      >
                        <MenuItem value={5}>5 seconds</MenuItem>
                        <MenuItem value={10}>10 seconds</MenuItem>
                        <MenuItem value={30}>30 seconds</MenuItem>
                        <MenuItem value={60}>1 minute</MenuItem>
                        <MenuItem value={300}>5 minutes</MenuItem>
                      </Select>
                    </FormControl>
                  </Box>
                )}
            </CollapsibleCard>

            <CollapsibleCard id="tg.moderation.escalation_chain" title="Escalation Chain" badge={<ProBadge />}>
                <FormControlLabel
                  control={<Switch checked={!!mod.escalation_enabled}
                    onChange={(e) => updateSetting('moderation.escalation_enabled', e.target.checked)} />}
                  label="Enable escalating punishments"
                />
                <Typography variant="body2" color="text.secondary" mb={2} mt={1}>
                  Instead of a single action, apply progressive punishments as warning count increases.
                </Typography>
                {(mod.escalation_steps || []).map((step, idx) => {
                  // Equal-width fields in a wrapping grid (2-up on mobile), with the
                  // delete control pinned to the step card's top-right — never
                  // stranded between fields.
                  const cell = { flex: '1 1 120px', minWidth: 0 };
                  return (
                  <Box key={idx} sx={{ position: 'relative', border: '1px solid', borderColor: 'divider', borderRadius: 1.5, p: 1.25, pt: 1.5, pr: 5, mb: 1 }}>
                    <IconButton size="small" color="error" onClick={() => {
                      const steps = (mod.escalation_steps || []).filter((_, i) => i !== idx);
                      updateSetting('moderation.escalation_steps', steps);
                    }} sx={{ position: 'absolute', top: 4, right: 4 }}>
                      <Delete fontSize="small" />
                    </IconButton>
                    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                      <TextField size="small" type="number" label="At warning #" sx={cell}
                        value={step.at_warning}
                        onChange={(e) => {
                          const steps = [...(mod.escalation_steps || [])];
                          steps[idx] = { ...steps[idx], at_warning: parseInt(e.target.value) };
                          updateSetting('moderation.escalation_steps', steps);
                        }} />
                      <FormControl size="small" sx={cell}>
                        <InputLabel>Action</InputLabel>
                        <Select value={step.action || 'mute'} label="Action"
                          onChange={(e) => {
                            const steps = [...(mod.escalation_steps || [])];
                            steps[idx] = { ...steps[idx], action: e.target.value };
                            updateSetting('moderation.escalation_steps', steps);
                          }}>
                          <MenuItem value="mute">Mute</MenuItem>
                          <MenuItem value="tempban">Temp Ban</MenuItem>
                          <MenuItem value="ban">Ban</MenuItem>
                        </Select>
                      </FormControl>
                      {step.action === 'mute' && (
                        <TextField size="small" type="number" label="Minutes" sx={cell}
                          value={step.duration_minutes || 60}
                          onChange={(e) => {
                            const steps = [...(mod.escalation_steps || [])];
                            steps[idx] = { ...steps[idx], duration_minutes: parseInt(e.target.value) };
                            updateSetting('moderation.escalation_steps', steps);
                          }} />
                      )}
                      {step.action === 'tempban' && (
                        <TextField size="small" type="number" label="Hours" sx={cell}
                          value={step.duration_hours || 24}
                          onChange={(e) => {
                            const steps = [...(mod.escalation_steps || [])];
                            steps[idx] = { ...steps[idx], duration_hours: parseInt(e.target.value) };
                            updateSetting('moderation.escalation_steps', steps);
                          }} />
                      )}
                      <Tooltip title="Only count warnings from the last N hours toward this step. Leave blank to count all of the user's warnings.">
                        <TextField size="small" type="number" label="Count within (hrs)" placeholder="All time" sx={cell}
                          value={step.time_window_hours ?? ''}
                          onChange={(e) => {
                            const steps = [...(mod.escalation_steps || [])];
                            const val = e.target.value === '' ? null : parseInt(e.target.value);
                            steps[idx] = { ...steps[idx], time_window_hours: val };
                            updateSetting('moderation.escalation_steps', steps);
                          }} />
                      </Tooltip>
                    </Box>
                  </Box>
                  );
                })}
                <Button size="small" startIcon={<Add />} onClick={() => {
                  const steps = [...(mod.escalation_steps || [])];
                  steps.push({ at_warning: (steps[steps.length - 1]?.at_warning || 1) + 1, action: 'mute', duration_minutes: 60 });
                  updateSetting('moderation.escalation_steps', steps);
                }} sx={{ mt: 1 }}>
                  Add Step
                </Button>
            </CollapsibleCard>

            <CollapsibleCard id="tg.moderation.auto_clean" title="Auto Clean System Messages">
                <Typography variant="body2" color="text.secondary" mb={2}>
                  Automatically delete Telegram system messages to keep your chat clean.
                </Typography>
                <FormControlLabel
                  control={<Switch checked={!!ac.enabled} onChange={(e) => updateSetting('auto_clean.enabled', e.target.checked)} />}
                  label="Enable Auto Clean"
                />
                <Divider sx={{ my: 2 }} />
                <Grid container spacing={1}>
                  {[
                    ['Delete join notifications', 'auto_clean.delete_joins', ac.delete_joins],
                    ['Delete leave notifications', 'auto_clean.delete_leaves', ac.delete_leaves],
                    ['Delete profile photo changes', 'auto_clean.delete_photo_changes', ac.delete_photo_changes],
                    ['Delete pinned message alerts', 'auto_clean.delete_pinned_messages', ac.delete_pinned_messages],
                    ['Delete forum topic events', 'auto_clean.delete_forum_events', ac.delete_forum_events],
                    ['Delete game score messages', 'auto_clean.delete_game_scores', ac.delete_game_scores],
                    ['Delete voice/video chat events', 'auto_clean.delete_voice_chat_events', ac.delete_voice_chat_events],
                    ['Delete bot command messages', 'auto_clean.delete_commands', ac.delete_commands],
                  ].map(([label, path, checked]) => (
                    <Grid item xs={12} sm={6} key={path}>
                      <FormControlLabel
                        control={<Switch checked={!!checked} onChange={(e) => updateSetting(path, e.target.checked)} />}
                        label={label}
                      />
                    </Grid>
                  ))}
                </Grid>
            </CollapsibleCard>

            <CollapsibleCard id="tg.moderation.auto_delete_notifications" title="Auto-Delete Notification Messages">
                <Typography variant="body2" color="text.secondary" mb={2}>
                  How long to keep AutoMod and moderation notification messages before deleting them. 0 = never delete.
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <TextField fullWidth type="number" label="Delete Warn Messages After (seconds, 0=never)"
                      inputProps={{ min: 0 }}
                      value={mod.auto_delete_warn_seconds ?? 0}
                      onChange={(e) => updateSetting('moderation.auto_delete_warn_seconds', parseInt(e.target.value) || 0)} />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <TextField fullWidth type="number" label="Delete Action Messages After (seconds, 0=never)"
                      inputProps={{ min: 0 }}
                      value={mod.auto_delete_action_seconds ?? 0}
                      onChange={(e) => updateSetting('moderation.auto_delete_action_seconds', parseInt(e.target.value) || 0)} />
                  </Grid>
                </Grid>
            </CollapsibleCard>
          </>
        )}

        {/* MODERATION › Reports */}
        {cat === 'moderation' && subTab === 2 && (
          <>
            <CollapsibleCard id="tg.moderation.reports_settings" title="Reports Settings">
                <FormControlLabel
                  control={<Switch checked={!!rep.enabled} onChange={(e) => updateSetting('reports.enabled', e.target.checked)} />}
                  label="Enable /report command"
                />
                <Grid container spacing={2} sx={{ mt: 1 }}>
                  <Grid item xs={12} sm={6}>
                    <FormControl fullWidth>
                      <InputLabel>Notify Admins</InputLabel>
                      <Select value={rep.notify_admins || 'all'} label="Notify Admins"
                        onChange={(e) => updateSetting('reports.notify_admins', e.target.value)}>
                        <MenuItem value="all">All admins</MenuItem>
                        <MenuItem value="selected">Selected admins only</MenuItem>
                      </Select>
                    </FormControl>
                  </Grid>
                </Grid>

                {rep.notify_admins === 'selected' && (
                  <Box sx={{ mt: 2 }}>
                    <Typography variant="subtitle2" fontWeight={600} mb={1}>Admins to receive report DMs</Typography>
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mb: 1.5, minHeight: 28 }}>
                      {(rep.selected_admin_ids || []).length === 0 ? (
                        <Typography variant="caption" color="text.secondary" sx={{ alignSelf: 'center' }}>None selected</Typography>
                      ) : (
                        (rep.selected_admin_ids || []).map(id => {
                          const adm = groupAdmins.find(a => a.user_id === id);
                          return (
                            <Chip
                              key={id}
                              size="small"
                              label={adm ? (adm.username ? `@${adm.username}` : adm.first_name) : String(id)}
                              onDelete={() => updateSetting('reports.selected_admin_ids', (rep.selected_admin_ids || []).filter(x => x !== id))}
                            />
                          );
                        })
                      )}
                    </Box>
                    <Button size="small" variant="outlined" onClick={(e) => setReportAdminAnchor(e.currentTarget)}>
                      Select Admins
                    </Button>
                    <Popover
                      open={Boolean(reportAdminAnchor)}
                      anchorEl={reportAdminAnchor}
                      onClose={() => setReportAdminAnchor(null)}
                      anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
                    >
                      <Box sx={{ p: 1.5, minWidth: 300, maxHeight: 350, overflowY: 'auto' }}>
                        {adminsLoading ? (
                          <CircularProgress size={20} />
                        ) : groupAdmins.length === 0 ? (
                          <Typography variant="caption" color="text.secondary">No admins found. Make sure @telegizer_bot is an admin.</Typography>
                        ) : (
                          <Stack spacing={0.5}>
                            {groupAdmins.map((admin) => {
                              const selected = (rep.selected_admin_ids || []).includes(admin.user_id);
                              return (
                                <Box key={admin.user_id} sx={{
                                  display: 'flex', alignItems: 'center', gap: 1, p: 0.75, borderRadius: 1,
                                  cursor: admin.can_dm ? 'pointer' : 'default',
                                  bgcolor: selected ? 'rgba(33,150,243,0.08)' : 'transparent',
                                  opacity: admin.can_dm ? 1 : 0.65,
                                  '&:hover': { bgcolor: admin.can_dm ? 'action.hover' : undefined },
                                }}
                                  onClick={() => {
                                    if (!admin.can_dm) return;
                                    const cur = rep.selected_admin_ids || [];
                                    updateSetting('reports.selected_admin_ids',
                                      selected ? cur.filter(id => id !== admin.user_id) : [...cur, admin.user_id]);
                                  }}>
                                  <Switch size="small" checked={selected} disabled={!admin.can_dm} onChange={() => {}} />
                                  <Box sx={{ flexGrow: 1 }}>
                                    <Typography variant="body2" fontWeight={500} sx={{ lineHeight: 1.2 }}>
                                      {admin.first_name}{admin.username ? ` (@${admin.username})` : ''}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">
                                      {admin.status === 'creator' ? 'Owner' : 'Admin'}
                                    </Typography>
                                  </Box>
                                  {admin.can_dm ? (
                                    <Chip label="✓ DM OK" color="success" size="small" sx={{ fontSize: '0.68rem', height: 20 }} />
                                  ) : (
                                    <Chip label="⚠ Start bot" color="warning" size="small" sx={{ fontSize: '0.68rem', height: 20 }} />
                                  )}
                                </Box>
                              );
                            })}
                          </Stack>
                        )}
                      </Box>
                    </Popover>
                    <Typography variant="caption" color="text.secondary" display="block" mt={1}>
                      Selected admins receive reports via private DM from @telegizer_bot. They must have started the bot first.
                    </Typography>
                  </Box>
                )}

                {rep.notify_admins === 'all' && (
                  <Alert severity="info" icon={false} sx={{ mt: 2 }}>
                    <Typography variant="caption">
                      Reports are sent as private DMs to all admins who have started @telegizer_bot.
                      Admins who have not started the bot are silently skipped.
                    </Typography>
                  </Alert>
                )}
            </CollapsibleCard>
            <CollapsibleCard id="tg.moderation.reported_messages" title="Reported Messages">
                <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}>
                  <Button size="small" onClick={fetchReports} disabled={reportsLoading}>Refresh</Button>
                </Box>
                {reportsLoading ? <CircularProgress size={24} /> : (
                  reports.length === 0 ? (
                    <Typography color="text.secondary">No reports yet.</Typography>
                  ) : isMobile ? (
                    <Stack spacing={1.5}>
                      {reports.map((r) => (
                        <Box key={r.id} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1.5, p: 1.5 }}>
                          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
                            <Chip label={r.status} size="small" color={r.status === 'open' ? 'warning' : 'success'} />
                            {r.status === 'open' && (
                              <Tooltip title="Mark resolved">
                                <IconButton size="small" color="success" onClick={() => handleResolveReport(r.id)}>
                                  <CheckCircle fontSize="small" />
                                </IconButton>
                              </Tooltip>
                            )}
                          </Box>
                          <Typography variant="body2" fontWeight={500}>
                            @{r.reporter_username || r.reporter_user_id} → @{r.reported_username || r.reported_user_id}
                          </Typography>
                          {r.reason && <Typography variant="caption" color="text.secondary" display="block" mt={0.25}>{r.reason}</Typography>}
                          <Typography variant="caption" color="text.disabled" display="block" mt={0.25}>
                            {r.created_at ? new Date(r.created_at).toLocaleDateString() : ''}
                          </Typography>
                        </Box>
                      ))}
                    </Stack>
                  ) : (
                    <TableContainer sx={{ overflowX: 'auto' }}>
                      <Table size="small" sx={{ minWidth: 500 }}>
                        <TableHead>
                          <TableRow>
                            <TableCell>Reporter</TableCell>
                            <TableCell>Reported User</TableCell>
                            <TableCell>Reason</TableCell>
                            <TableCell>Status</TableCell>
                            <TableCell>Date</TableCell>
                            <TableCell>Action</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {reports.map((r) => (
                            <TableRow key={r.id} hover>
                              <TableCell>@{r.reporter_username || r.reporter_user_id}</TableCell>
                              <TableCell>@{r.reported_username || r.reported_user_id}</TableCell>
                              <TableCell>{r.reason || '-'}</TableCell>
                              <TableCell>
                                <Chip label={r.status} size="small"
                                  color={r.status === 'open' ? 'warning' : 'success'} />
                              </TableCell>
                              <TableCell>
                                <Typography variant="caption">{r.created_at ? new Date(r.created_at).toLocaleDateString() : '-'}</Typography>
                              </TableCell>
                              <TableCell>
                                {r.status === 'open' && (
                                  <Tooltip title="Mark resolved">
                                    <IconButton size="small" color="success"
                                      onClick={() => handleResolveReport(r.id)}>
                                      <CheckCircle fontSize="small" />
                                    </IconButton>
                                  </Tooltip>
                                )}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  )
                )}
            </CollapsibleCard>
          </>
        )}

        {/* ══════════════════════════════════════════════════════════
            MEMBERS
        ══════════════════════════════════════════════════════════ */}

        {/* MEMBERS › Verification */}
        {cat === 'members' && subTab === 0 && (
          <>
          <CollapsibleCard id="tg.members.verification" title="Verification Settings">
              <FormControlLabel
                control={<Switch checked={!!v.enabled} onChange={(e) => updateSetting('verification.enabled', e.target.checked)} />}
                label="Enable verification for new members"
              />
              <Divider sx={{ my: 2 }} />
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6}>
                  <FormControl fullWidth>
                    <InputLabel>Verification Method</InputLabel>
                    <Select value={v.method || 'button'} label="Verification Method"
                      onChange={(e) => updateSetting('verification.method', e.target.value)}>
                      <MenuItem value="button">Button Click</MenuItem>
                      <MenuItem value="math">Math Captcha</MenuItem>
                      <MenuItem value="word">Word Captcha</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField fullWidth type="number" label="Timeout (seconds)"
                    value={v.timeout_seconds || 60}
                    onChange={(e) => updateSetting('verification.timeout_seconds', parseInt(e.target.value))} />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <FormControl fullWidth>
                    <InputLabel>On Failure</InputLabel>
                    <Select value={v.kick_on_fail ? 'true' : 'false'} label="On Failure"
                      onChange={(e) => updateSetting('verification.kick_on_fail', e.target.value === 'true')}>
                      <MenuItem value="true">Kick unverified users</MenuItem>
                      <MenuItem value="false">Restrict until verified</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField fullWidth type="number" label="Max Verification Attempts"
                    value={v.max_attempts ?? 3}
                    onChange={(e) => updateSetting('verification.max_attempts', parseInt(e.target.value))} />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <FormControl fullWidth>
                    <InputLabel>Trigger Verification</InputLabel>
                    <Select value={v.verify_on || 'join'} label="Trigger Verification"
                      onChange={(e) => updateSetting('verification.verify_on', e.target.value)}>
                      <MenuItem value="join">On Join</MenuItem>
                      <MenuItem value="first_message">On First Message</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
              </Grid>

              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle2" fontWeight={600} mb={1}>Auto-Delete</Typography>
              <FormControlLabel
                control={
                  <Switch
                    checked={v.auto_delete_on_timeout !== false}
                    onChange={(e) => updateSetting('verification.auto_delete_on_timeout', e.target.checked)}
                  />
                }
                label={
                  <Box>
                    <Typography variant="body2">Auto-delete verification message on timeout</Typography>
                    <Typography variant="caption" color="text.secondary">
                      When enabled, the challenge message is automatically deleted after {v.timeout_seconds || 300} seconds
                      — keeping the group clean even if the user never responds.
                    </Typography>
                  </Box>
                }
              />

              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle2" fontWeight={600} mb={1}>Verification Location</Typography>
              <Typography variant="body2" color="text.secondary" mb={2}>
                Where the bot sends the verification prompt when a new member joins.
              </Typography>
              <FormControl fullWidth sx={{ mb: 2 }}>
                <InputLabel>Verification Location</InputLabel>
                <Select
                  value={v.destination || 'same_group'}
                  label="Verification Location"
                  onChange={(e) => updateSetting('verification.destination', e.target.value)}
                >
                  <MenuItem value="same_group">Same group — verification appears in the group chat</MenuItem>
                  <MenuItem value="topic">Group topic / forum thread</MenuItem>
                  <MenuItem value="dedicated_group">Dedicated verification group</MenuItem>
                  <MenuItem value="channel">Verification channel</MenuItem>
                </Select>
              </FormControl>

              {(v.destination === 'topic') && (
                <TextField
                  fullWidth
                  label="Verification Topic"
                  placeholder="e.g. 12345 or https://t.me/c/123/456"
                  value={v.destination_topic_id || ''}
                  onChange={(e) => {
                    const parsed = parseTopicInput(e.target.value);
                    updateSetting('verification.destination_topic_id', parsed ? String(parsed) : e.target.value);
                  }}
                  helperText="Paste a Telegram topic link or enter the topic ID. Leave blank for main group chat."
                  sx={{ mb: 2 }}
                />
              )}

              {(v.destination === 'dedicated_group' || v.destination === 'channel') && (
                <TextField fullWidth
                  label={v.destination === 'channel' ? 'Channel ID' : 'Group ID'}
                  sx={{ mb: 2 }}
                  value={v.destination_chat_id || ''}
                  onChange={(e) => updateSetting('verification.destination_chat_id', e.target.value)}
                  helperText={
                    v.destination === 'channel'
                      ? 'Telegram channel ID (e.g. -1001234567890). Bot must be an admin there.'
                      : 'Telegram group ID (e.g. -1001234567890). Bot must be a member there.'
                  } />
              )}

              {v.destination && v.destination !== 'same_group' && (
                <Alert severity="info" icon={false}>
                  <Typography variant="caption">
                    Make sure @telegizer_bot is an admin (or at least a member) in the destination and has permission to send messages.
                  </Typography>
                </Alert>
              )}
          </CollapsibleCard>

          <InlineCmdRouting
            id="tg.members.verification_command_routing"
            cmds={['/verify']}
            title="Verification Command Routing"
            description="Control which forum topics the /verify command is allowed in."
            cmdRouting={cmdRouting}
            setCmdRouting={setCmdRouting}
            saving={routingSaving}
            onSave={handleSaveCmdRouting}
          />
          </>
        )}

        {/* MEMBERS › Welcome */}
        {cat === 'members' && subTab === 1 && (
          <>
            <CollapsibleCard id="tg.members.welcome_message" title="Welcome Message">
                <FormControlLabel
                  control={<Switch checked={!!w.enabled} onChange={(e) => updateSetting('welcome.enabled', e.target.checked)} />}
                  label="Send welcome message to new members"
                />
                <Divider sx={{ my: 2 }} />
                <FormControlLabel
                  control={<Switch checked={!!w.ai_welcome_enabled}
                    onChange={(e) => updateSetting('welcome.ai_welcome_enabled', e.target.checked)} />}
                  label={<Box sx={{ display: 'flex', alignItems: 'center' }}>AI-generated welcome messages (requires OpenAI API key)<ProBadge /></Box>}
                />
                {!w.ai_welcome_enabled && (
                  <TextField fullWidth multiline rows={4} label="Welcome Message" sx={{ mt: 2, mb: 2 }}
                    value={w.message || ''}
                    onChange={(e) => updateSetting('welcome.message', e.target.value)}
                    helperText="Placeholders: {first_name}, {group_name}, {member_count}, {username}" />
                )}
                {w.ai_welcome_enabled && (
                  <Alert severity="info" sx={{ mt: 2, mb: 2 }}>
                    {settingsData?.workspace_ai_key_set
                      ? 'AI welcome messages are active using the Telegizer platform AI. You can add your own OpenAI key in AI & Integrations if preferred.'
                      : 'AI welcome messages require an OpenAI API key. Add your key in AI & Integrations → Knowledge Base.'}
                  </Alert>
                )}
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <TextField fullWidth type="number" label="Auto-delete after (seconds, 0 = never)"
                      value={w.delete_after_seconds || 0}
                      onChange={(e) => updateSetting('welcome.delete_after_seconds', parseInt(e.target.value))} />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <ForumTopicSelector
                      botId={botId}
                      groupId={groupId}
                      value={w.topic_id || null}
                      onChange={(id) => updateSetting('welcome.topic_id', id)}
                      label="Welcome Topic"
                      helperText="Topic where welcome messages are sent."
                    />
                  </Grid>
                  <Grid item xs={12}>
                    <FormControlLabel
                      control={<Switch checked={!!w.show_rules} onChange={(e) => updateSetting('welcome.show_rules', e.target.checked)} />}
                      label="Show rules in welcome message"
                    />
                  </Grid>
                  {w.show_rules && (
                    <Grid item xs={12}>
                      <TextField fullWidth multiline rows={4} label="Rules Text"
                        value={w.rules_text || ''}
                        onChange={(e) => updateSetting('welcome.rules_text', e.target.value)} />
                    </Grid>
                  )}
                </Grid>
            </CollapsibleCard>

            {!isOfficial && (
              <CollapsibleCard id="tg.members.private_welcome_dm" title="Private Welcome DM">
                  <Typography variant="body2" color="text.secondary" mb={2}>
                    Send a private message to each new member in addition to the group welcome.
                  </Typography>
                  <Alert severity="warning" sx={{ mb: 2 }}>
                    DMs only work for users who have already started this bot in Telegram. Sending unsolicited DMs may cause Telegram to restrict your bot.
                  </Alert>
                  <FormControlLabel
                    control={<Switch checked={!!w.dm_enabled} onChange={e => updateSetting('welcome.dm_enabled', e.target.checked)} />}
                    label="Send DM to new members"
                  />
                  {w.dm_enabled && (
                    <TextField fullWidth multiline rows={3} label="DM Message" sx={{ mt: 2 }}
                      value={w.dm_message || ''}
                      onChange={e => updateSetting('welcome.dm_message', e.target.value)}
                      helperText="Placeholders: {first_name}, {group_name}, {username}" />
                  )}
              </CollapsibleCard>
            )}
          </>
        )}

        {/* MEMBERS › XP & Roles */}
        {cat === 'members' && subTab === 2 && (
          <>
            <CollapsibleCard id="tg.members.xp_level_system" title="XP & Level System">
                <FormControlLabel
                  control={<Switch checked={!!l.enabled} onChange={(e) => updateSetting('levels.enabled', e.target.checked)} />}
                  label="Enable XP and leveling system"
                />
                <Divider sx={{ my: 2 }} />
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={4}>
                    <TextField fullWidth type="number" label="XP per Message"
                      value={l.xp_per_message || 10}
                      onChange={(e) => updateSetting('levels.xp_per_message', parseInt(e.target.value))} />
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <TextField fullWidth type="number" label="XP Cooldown (seconds)"
                      value={l.xp_cooldown_seconds || 60}
                      onChange={(e) => updateSetting('levels.xp_cooldown_seconds', parseInt(e.target.value))} />
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <TextField
                      fullWidth
                      label="Level-up Topic"
                      placeholder="e.g. 12345 or https://t.me/c/123/456"
                      value={l.levelup_topic_id || ''}
                      onChange={(e) => {
                        const parsed = parseTopicInput(e.target.value);
                        updateSetting('levels.levelup_topic_id', parsed ? String(parsed) : e.target.value);
                      }}
                      helperText="Paste a Telegram topic link or enter the topic ID. Leave blank for main group chat."
                    />
                  </Grid>
                  <Grid item xs={12} sm={8}>
                    <TextField fullWidth label="Level-up Message"
                      value={l.level_up_message || ''}
                      onChange={(e) => updateSetting('levels.level_up_message', e.target.value)}
                      helperText="Placeholders: {first_name}, {level}" />
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <FormControlLabel
                      control={<Switch checked={!!l.announce_level_up}
                        onChange={(e) => updateSetting('levels.announce_level_up', e.target.checked)} />}
                      label="Announce level-ups"
                      sx={{ mt: 1 }}
                    />
                  </Grid>
                  <Grid item xs={12}>
                    <FormControlLabel
                      control={<Switch checked={!!l.ai_levelup_enabled}
                        onChange={(e) => updateSetting('levels.ai_levelup_enabled', e.target.checked)} />}
                      label={<Box sx={{ display: 'flex', alignItems: 'center' }}>AI-generated level-up messages (requires OpenAI API key)<ProBadge /></Box>}
                    />
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <TextField fullWidth type="number" label="XP per Reaction"
                      value={l.xp_per_reaction ?? 10}
                      onChange={(e) => updateSetting('levels.xp_per_reaction', parseInt(e.target.value))} />
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <TextField fullWidth type="number" label="Reaction XP Cooldown (s)"
                      value={l.xp_reaction_cooldown_seconds ?? 30}
                      onChange={(e) => updateSetting('levels.xp_reaction_cooldown_seconds', parseInt(e.target.value))} />
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <TextField fullWidth type="number" label="Delete Level-Up Message After (s, 0=never)"
                      value={l.delete_levelup_after_seconds ?? 0}
                      onChange={(e) => updateSetting('levels.delete_levelup_after_seconds', parseInt(e.target.value))} />
                  </Grid>
                </Grid>
            </CollapsibleCard>

            <CollapsibleCard id="tg.members.xp_penalties" title="XP Penalties (Moderation Actions)" sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary" mb={2}>XP deducted when a moderation action is applied to a member.</Typography>
                <Grid container spacing={2}>
                  <Grid item xs={6} sm={3}>
                    <TextField fullWidth type="number" label="Warn Penalty"
                      value={l.xp_penalty_warn ?? -10}
                      onChange={(e) => updateSetting('levels.xp_penalty_warn', parseInt(e.target.value))} />
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <TextField fullWidth type="number" label="Mute Penalty"
                      value={l.xp_penalty_mute ?? -20}
                      onChange={(e) => updateSetting('levels.xp_penalty_mute', parseInt(e.target.value))} />
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <TextField fullWidth type="number" label="Kick Penalty"
                      value={l.xp_penalty_kick ?? -30}
                      onChange={(e) => updateSetting('levels.xp_penalty_kick', parseInt(e.target.value))} />
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <TextField fullWidth type="number" label="Ban Penalty"
                      value={l.xp_penalty_ban ?? -50}
                      onChange={(e) => updateSetting('levels.xp_penalty_ban', parseInt(e.target.value))} />
                  </Grid>
                </Grid>
            </CollapsibleCard>

            <CollapsibleCard id="tg.members.rank_card_style" title="Rank Card Style" sx={{ mb: 2 }}>
                <Grid container spacing={2} alignItems="center">
                  <Grid item xs={12} sm={4}>
                    <Typography variant="body2" color="text.secondary" mb={0.5}>Background Start</Typography>
                    <input type="color"
                      value={(l.rank_card || {}).bg_color_start || '#1a1a2e'}
                      onChange={(e) => updateSetting('levels.rank_card.bg_color_start', e.target.value)}
                      style={{ width: '100%', height: 40, borderRadius: 8, border: '1px solid #30363d', cursor: 'pointer' }} />
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <Typography variant="body2" color="text.secondary" mb={0.5}>Background End</Typography>
                    <input type="color"
                      value={(l.rank_card || {}).bg_color_end || '#16213e'}
                      onChange={(e) => updateSetting('levels.rank_card.bg_color_end', e.target.value)}
                      style={{ width: '100%', height: 40, borderRadius: 8, border: '1px solid #30363d', cursor: 'pointer' }} />
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <Typography variant="body2" color="text.secondary" mb={0.5}>Accent Color</Typography>
                    <input type="color"
                      value={(l.rank_card || {}).accent_color || '#2196f3'}
                      onChange={(e) => updateSetting('levels.rank_card.accent_color', e.target.value)}
                      style={{ width: '100%', height: 40, borderRadius: 8, border: '1px solid #30363d', cursor: 'pointer' }} />
                  </Grid>
                </Grid>
            </CollapsibleCard>

            <CollapsibleCard id="tg.members.roles" title="Roles">
                <Typography variant="body2" color="text.secondary" mb={2}>
                  Members are automatically assigned a role when they reach the specified level. Use <code>/roles</code> in Telegram to display the list.
                </Typography>
                <Divider sx={{ mb: 2 }} />
                {(l.roles || []).map((role, idx) => (
                  <Box key={idx} sx={{ display: 'flex', gap: 2, mb: 1.5, alignItems: 'center' }}>
                    <TextField size="small" type="number" label="From Level" sx={{ width: 110 }}
                      value={role.level}
                      onChange={(e) => {
                        const roles = [...(l.roles || [])];
                        roles[idx] = { ...roles[idx], level: parseInt(e.target.value) };
                        updateSetting('levels.roles', roles);
                      }} />
                    <TextField size="small" label="Role Name" sx={{ flexGrow: 1 }}
                      value={role.name}
                      onChange={(e) => {
                        const roles = [...(l.roles || [])];
                        roles[idx] = { ...roles[idx], name: e.target.value };
                        updateSetting('levels.roles', roles);
                      }} />
                    <IconButton size="small" color="error" onClick={() => {
                      const roles = (l.roles || []).filter((_, i) => i !== idx);
                      updateSetting('levels.roles', roles);
                    }}>
                      <Delete fontSize="small" />
                    </IconButton>
                  </Box>
                ))}
                <Button size="small" startIcon={<Add />} sx={{ mt: 1 }} onClick={() => {
                  const roles = [...(l.roles || [])];
                  const maxLevel = roles.reduce((m, r) => Math.max(m, r.level), 0);
                  roles.push({ level: maxLevel + 10, name: 'New Role' });
                  updateSetting('levels.roles', roles);
                }}>
                  Add Role
                </Button>
            </CollapsibleCard>

            <InlineCmdRouting
              id="tg.members.role_command_routing"
              cmds={['/role']}
              title="Role Command Routing"
              description="Control which forum topics the /role command is allowed in."
              cmdRouting={cmdRouting}
              setCmdRouting={setCmdRouting}
              saving={routingSaving}
              onSave={handleSaveCmdRouting}
            />

            <CollapsibleCard id="tg.members.xp_command_routing" title="XP Command Routing" sx={{ mt: 2 }}>
                <Typography variant="body2" color="text.secondary" mb={2}>
                  Control which forum topics the <code>/xp</code>, <code>/rank</code>, and <code>/leaderboard</code> commands are allowed in.
                  Only applies when the group has Telegram forum topics enabled.
                </Typography>
                <Divider sx={{ mb: 2 }} />
                {['/xp', '/rank', '/leaderboard'].map((cmd) => {
                  const rule = (cmdRouting.commands || {})[cmd] || { scope: 'all_group', topic_ids: [] };
                  const topics = cmdRouting.topics || [];
                  return (
                    <Box key={cmd} sx={{ mb: 2 }}>
                      <Stack direction={{ xs: 'column', sm: 'row' }} alignItems={{ xs: 'stretch', sm: 'center' }} spacing={{ xs: 1, sm: 2 }} mb={1}>
                        <Typography fontWeight={600} sx={{ minWidth: { sm: 130 }, fontFamily: 'monospace' }}>{cmd}</Typography>
                        <FormControl size="small" sx={{ minWidth: 200, width: { xs: '100%', sm: 'auto' } }}>
                          <InputLabel>Access</InputLabel>
                          <Select
                            value={rule.scope}
                            label="Access"
                            onChange={(e) => {
                              setCmdRouting((prev) => ({
                                ...prev,
                                commands: { ...prev.commands, [cmd]: { ...rule, scope: e.target.value } },
                              }));
                            }}
                          >
                            {SCOPE_OPTIONS.map((o) => (
                              <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </Stack>

                      {rule.scope === 'specific_topics' && (
                        <Box sx={{ ml: 0.5 }}>
                          {topics.length === 0 ? (
                            <TextField
                              size="small"
                              fullWidth
                              label="Topic ID or link"
                              placeholder="e.g. 12345 or https://t.me/c/123/456"
                              value={rule.manual_topic_input || (rule.topic_ids?.[0] ? String(rule.topic_ids[0]) : '')}
                              onChange={(e) => {
                                const raw = e.target.value;
                                const parsed = parseTopicInput(raw);
                                setCmdRouting((prev) => ({
                                  ...prev,
                                  commands: {
                                    ...prev.commands,
                                    [cmd]: { ...rule, manual_topic_input: raw, topic_ids: parsed ? [String(parsed)] : [] },
                                  },
                                }));
                              }}
                              helperText="No forum topics detected yet. Paste a Telegram topic link or enter the topic ID directly."
                            />
                          ) : (
                            <Stack direction="row" flexWrap="wrap" gap={1}>
                              {topics.map((t) => {
                                const checked = (rule.topic_ids || []).includes(String(t.thread_id));
                                return (
                                  <FormControlLabel
                                    key={t.thread_id}
                                    control={
                                      <Switch
                                        size="small"
                                        checked={checked}
                                        onChange={(e) => {
                                          const current = rule.topic_ids || [];
                                          const updated = e.target.checked
                                            ? [...new Set([...current, String(t.thread_id)])]
                                            : current.filter((id) => id !== String(t.thread_id));
                                          setCmdRouting((prev) => ({
                                            ...prev,
                                            commands: { ...prev.commands, [cmd]: { ...rule, topic_ids: updated } },
                                          }));
                                        }}
                                      />
                                    }
                                    label={t.name}
                                  />
                                );
                              })}
                            </Stack>
                          )}
                        </Box>
                      )}
                    </Box>
                  );
                })}
                <Button
                  variant="contained"
                  size="small"
                  disabled={saving}
                  onClick={handleSaveCmdRouting}
                  sx={{ mt: 1 }}
                >
                  {saving ? <CircularProgress size={16} sx={{ mr: 1 }} /> : null}
                  Save Routing
                </Button>
            </CollapsibleCard>
          </>
        )}

        {/* ══════════════════════════════════════════════════════════
            AUTOMATION
        ══════════════════════════════════════════════════════════ */}

        {/* AUTOMATION › Scheduler */}
        {cat === 'automation' && subTab === 0 && (
          <>
            <DefaultTimezoneCard
              value={settingsData?.timezone || 'UTC'}
              onChange={tz => updateSetting('timezone', tz)}
            />
            <ScheduledMessages botId={botId} groupId={groupId} defaultTimezone={settingsData?.timezone || 'UTC'} />
          </>
        )}

        {/* AUTOMATION › Auto Reply */}
        {cat === 'automation' && subTab === autoReplySubTabIdx && (
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <Box>
                  <Typography variant="h6" fontWeight={600}>Auto Response Triggers</Typography>
                  <Typography variant="body2" color="text.secondary">
                    Bot auto-replies when a message matches a trigger keyword.
                  </Typography>
                </Box>
                <Button variant="contained" startIcon={<Add />} onClick={() => setArDialogOpen(true)}>
                  Add Trigger
                </Button>
              </Box>
              {autoResponses.length === 0 ? (
                <Typography color="text.secondary">No triggers configured yet.</Typography>
              ) : isMobile ? (
                <Stack spacing={1.5}>
                  {autoResponses.map((ar) => (
                    <Box key={ar.id} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1.5, p: 1.5 }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 0.5 }}>
                        <Typography variant="body2" sx={{ fontFamily: 'monospace', fontWeight: 600, wordBreak: 'break-all' }}>
                          {ar.trigger_text}
                        </Typography>
                        <IconButton size="small" color="error" sx={{ flexShrink: 0, ml: 0.5 }}
                          onClick={() => handleDeleteAutoResponse(ar.id)}>
                          <Delete fontSize="small" />
                        </IconButton>
                      </Box>
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 0.75, fontSize: '0.8rem' }} noWrap>
                        {ar.response_text}
                      </Typography>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                        <Chip label={ar.match_type} size="small" />
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25 }}>
                          <Typography variant="caption" color="text.secondary">On</Typography>
                          <Switch size="small" checked={ar.is_enabled} onChange={() => handleToggleAutoResponse(ar)} />
                        </Box>
                        <Tooltip title={ar.use_as_ai_knowledge ? 'AI uses this as knowledge' : 'Let AI use as knowledge'}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25 }}>
                            <SmartToy fontSize="small" color={ar.use_as_ai_knowledge ? 'primary' : 'disabled'} />
                            <Switch size="small" checked={!!ar.use_as_ai_knowledge}
                              onChange={() => handleToggleAiKnowledge(ar)} color="secondary" />
                          </Box>
                        </Tooltip>
                      </Box>
                    </Box>
                  ))}
                </Stack>
              ) : (
                <TableContainer sx={{ overflowX: 'auto' }}>
                  <Table size="small" sx={{ minWidth: 420 }}>
                    <TableHead>
                      <TableRow>
                        <TableCell>Trigger</TableCell>
                        <TableCell>Response</TableCell>
                        <TableCell>Match</TableCell>
                        <TableCell>Enabled</TableCell>
                        <TableCell>
                          <Tooltip title="Use this trigger as AI knowledge so the AI can answer related questions semantically">
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                              <SmartToy fontSize="small" color="primary" />
                              <span>AI</span>
                            </Box>
                          </Tooltip>
                        </TableCell>
                        <TableCell>Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {autoResponses.map((ar) => (
                        <TableRow key={ar.id} hover>
                          <TableCell><code>{ar.trigger_text}</code></TableCell>
                          <TableCell sx={{ maxWidth: 200 }}>
                            <Typography variant="body2" noWrap>{ar.response_text}</Typography>
                          </TableCell>
                          <TableCell><Chip label={ar.match_type} size="small" /></TableCell>
                          <TableCell>
                            <Switch size="small" checked={ar.is_enabled}
                              onChange={() => handleToggleAutoResponse(ar)} />
                          </TableCell>
                          <TableCell>
                            <Tooltip title={ar.use_as_ai_knowledge ? 'AI uses this as knowledge — click to disable' : 'Enable to let AI use this as knowledge'}>
                              <Switch
                                size="small"
                                checked={!!ar.use_as_ai_knowledge}
                                onChange={() => handleToggleAiKnowledge(ar)}
                                color="secondary"
                              />
                            </Tooltip>
                          </TableCell>
                          <TableCell>
                            <IconButton size="small" color="error"
                              onClick={() => handleDeleteAutoResponse(ar.id)}>
                              <Delete fontSize="small" />
                            </IconButton>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </CardContent>
          </Card>
        )}

        {/* AUTOMATION › Polls */}
        {cat === 'automation' && subTab === pollsSubTabIdx && (
          <>
            <DefaultTimezoneCard
              value={settingsData?.timezone || 'UTC'}
              onChange={tz => updateSetting('timezone', tz)}
            />
            <PollCreator botId={botId} groupId={groupId} defaultTimezone={settingsData?.timezone || 'UTC'} />
          </>
        )}

        {/* AUTOMATION › Forwarding — per-group, source fixed to this group */}
        {cat === 'automation' && subTab === forwardingSubTabIdx && forwardingSubTabIdx >= 0 && (
          <WorkspaceForwarding embeddedGroupId={groupChatId} embeddedGroupName={groupDisplayName} />
        )}

        {/* AUTOMATION › Workflows — per-group, source fixed to this group */}
        {cat === 'automation' && subTab === workflowsSubTabIdx && workflowsSubTabIdx >= 0 && (
          <WorkspaceAutomations embeddedGroupId={groupChatId} />
        )}

        {/* AUTOMATION › Webhooks — moved here from AI & Integrations (O2) */}
        {cat === 'automation' && subTab === webhooksSubTabIdx && webhooksSubTabIdx >= 0 && (
          <>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6" fontWeight={600}>Webhooks</Typography>
              <EntBadge />
            </Box>
            <WebhookManager botId={botId} groupId={groupId} />
          </>
        )}


        {/* ══════════════════════════════════════════════════════════
            COMMUNITY
        ══════════════════════════════════════════════════════════ */}

        {/* COMMUNITY › Raids — the standalone "Create Raid" button was removed;
            raids are now created as a campaign (Campaigns → Twitter Raid) so there
            is a single, richer creation flow. This tab just points there. */}
        {cat === 'community' && subTab === 0 && (
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <Typography variant="h6" fontWeight={600}>Raid Manager</Typography>
                <ProBadge />
              </Box>
              <Typography variant="body2" color="text.secondary" mb={2}>
                Coordinate Twitter/X raids with your community. Members earn XP for participating.
                Raids are now created as a campaign — pick <strong>Twitter Raid</strong> when creating one.
              </Typography>
              <Button variant="contained" startIcon={<Campaign />} onClick={() => { setCat('community'); setSubTab(2); }}>
                Go to Campaigns
              </Button>
            </CardContent>
          </Card>
        )}

        {/* COMMUNITY › Invite Links */}
        {cat === 'community' && subTab === 1 && (
          <>
            <CollapsibleCard id="tg.community.invite_command_topic" title="Invite Command Topic" sx={{ mb: 2 }}>
                <ForumTopicSelector
                  botId={botId}
                  groupId={groupId}
                  value={settingsData?.invites?.allowed_topic_id || null}
                  onChange={(id) => updateSetting('invites.allowed_topic_id', id)}
                  label="Allowed Topic"
                  helperText="If set, /invitelink only works in this topic. Other topics: silent ignore."
                />
            </CollapsibleCard>
            <InviteLinks botId={botId} groupId={groupId} />
            <InlineCmdRouting
              id="tg.community.invite_command_routing"
              cmds={['/invite', '/ref']}
              title="Invite Command Routing"
              description="Control which forum topics invite and referral commands are allowed in."
              cmdRouting={cmdRouting}
              setCmdRouting={setCmdRouting}
              saving={routingSaving}
              onSave={handleSaveCmdRouting}
            />
          </>
        )}

        {/* COMMUNITY › Campaigns */}
        {cat === 'community' && subTab === 2 && (
          <CampaignManager botId={botId} groupId={groupId} userTier={userTier} />
        )}

        {/* ══════════════════════════════════════════════════════════
            AI & INTEGRATIONS
        ══════════════════════════════════════════════════════════ */}

        {/* AI › Knowledge Base */}
        {cat === 'ai' && subTab === 0 && (
          <>
            <KnowledgeBase botId={botId} groupId={groupId} settings={settingsData} updateSetting={updateSetting} />
            <InlineCmdRouting
              id="tg.ai.command_routing"
              cmds={['/ask']}
              title="AI Command Routing"
              description="Control which forum topics the /ask command is allowed in."
              cmdRouting={cmdRouting}
              setCmdRouting={setCmdRouting}
              saving={routingSaving}
              onSave={handleSaveCmdRouting}
            />
          </>
        )}

        {/* AI › Escalation — global settings for all AI + Automation triggers */}
        {cat === 'ai' && subTab === escalationSubTabIdx && (() => {
          const esc = settingsData?.escalation || {};
          const adminIds = esc.admin_ids || [];
          return (
            <>
              <Typography variant="h6" fontWeight={600} mb={2}>Global Escalation</Typography>
              <Alert severity="info" sx={{ mb: 2 }} icon={false}>
                When enabled, any AI or Automation issue (low-confidence KB reply, image AI, command failures)
                is privately forwarded to your selected admins instead of a public reply.
                Admins reply directly to the bot DM — the answer is auto-saved into the Knowledge Base.
              </Alert>

              <CollapsibleCard id="tg.ai.global_escalation" title="Global Escalation" sx={{ mb: 2 }}>
                  <FormControlLabel
                    control={<Switch checked={!!esc.enabled}
                      onChange={(e) => updateSetting('escalation.enabled', e.target.checked)} />}
                    label="Enable global escalation"
                  />
                  <Typography variant="caption" color="text.secondary" display="block" mb={2}>
                    When on, the bot suppresses public replies for unsure situations and DMs admins instead.
                  </Typography>

                  <Typography variant="subtitle2" fontWeight={600} mb={1}>Escalation Admins</Typography>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mb: 1.5, minHeight: 28 }}>
                    {adminIds.length === 0 ? (
                      <Typography variant="caption" color="text.secondary" sx={{ alignSelf: 'center' }}>None selected</Typography>
                    ) : (
                      adminIds.map((aid, idx) => {
                        const adm = groupAdmins.find(a => String(a.user_id) === String(aid) || a.username === aid.replace(/^@/, ''));
                        const label = adm ? (adm.username ? `@${adm.username}` : adm.first_name) : String(aid);
                        return (
                          <Chip
                            key={idx}
                            size="small"
                            label={label}
                            onDelete={() => updateSetting('escalation.admin_ids', adminIds.filter((_, i) => i !== idx))}
                          />
                        );
                      })
                    )}
                  </Box>
                  {adminsLoading ? (
                    <CircularProgress size={20} />
                  ) : groupAdmins.length > 0 ? (
                    <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1.5, overflow: 'hidden' }}>
                      {groupAdmins.map((admin, idx) => {
                        const selected = adminIds.some(aid => String(aid) === String(admin.user_id) || aid.replace(/^@/, '') === admin.username);
                        return (
                          <Box key={admin.user_id} sx={{
                            display: 'flex', alignItems: 'center', gap: 1, px: 1.5, py: 0.75,
                            borderBottom: idx < groupAdmins.length - 1 ? '1px solid' : 'none',
                            borderColor: 'divider',
                            cursor: admin.can_dm ? 'pointer' : 'default',
                            bgcolor: selected ? 'rgba(33,150,243,0.07)' : 'transparent',
                            opacity: admin.can_dm ? 1 : 0.65,
                            '&:hover': { bgcolor: admin.can_dm ? 'action.hover' : undefined },
                          }}
                            onClick={() => {
                              if (!admin.can_dm) return;
                              const newIds = selected
                                ? adminIds.filter(aid => String(aid) !== String(admin.user_id) && aid.replace(/^@/, '') !== admin.username)
                                : [...adminIds, String(admin.user_id)];
                              updateSetting('escalation.admin_ids', newIds);
                            }}>
                            <Switch size="small" checked={selected} disabled={!admin.can_dm} onChange={() => {}} />
                            <Box sx={{ flexGrow: 1 }}>
                              <Typography variant="body2" fontWeight={500} sx={{ lineHeight: 1.2 }}>
                                {admin.first_name}{admin.username ? ` (@${admin.username})` : ''}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {admin.status === 'creator' ? 'Owner' : 'Admin'}
                              </Typography>
                            </Box>
                            {admin.can_dm ? (
                              <Chip label="✓ Can receive DM" color="success" size="small" sx={{ fontSize: '0.68rem', height: 20 }} />
                            ) : (
                              <Tooltip title="Ask this admin to open the bot and press Start.">
                                <Chip label="⚠ Must start bot" color="warning" size="small" sx={{ fontSize: '0.68rem', height: 20 }} />
                              </Tooltip>
                            )}
                          </Box>
                        );
                      })}
                    </Box>
                  ) : (
                    <Alert severity="info" icon={false} sx={{ mb: 1 }}>
                      <Typography variant="caption">No group admins loaded yet. Switch to another tab and back, or save settings first.</Typography>
                    </Alert>
                  )}
                  <Box sx={{ mt: 1.5, display: 'flex', alignItems: 'center', gap: 1 }}>
                    <TextField
                      size="small"
                      placeholder="Or enter Telegram ID / @username manually…"
                      sx={{ flex: 1 }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && e.target.value.trim()) {
                          updateSetting('escalation.admin_ids', [...adminIds, e.target.value.trim()]);
                          e.target.value = '';
                        }
                      }}
                    />
                    <Typography variant="caption" color="text.secondary">Press Enter to add</Typography>
                  </Box>
                  <Typography variant="caption" color="text.secondary" display="block" mt={1}>
                    Selected admins receive a private DM when any AI or Automation issue occurs. They must have started the bot first.
                  </Typography>
              </CollapsibleCard>

              <CollapsibleCard id="tg.ai.escalation_types" title="Escalation Types" sx={{ mb: 2 }}>
                  {[
                    { key: 'ai_kb',      label: '🤖 AI Knowledge Base',  desc: 'Escalate when KB auto-reply confidence is low' },
                    { key: 'ai_image',   label: '🖼️ AI Image Review',    desc: 'Escalate low-confidence image AI results' },
                    { key: 'automation', label: '⚙️ Automation Errors',  desc: 'Escalate scheduled post / poll failures' },
                    { key: 'command',    label: '📌 Unknown Commands',    desc: 'Escalate unrecognised bot commands' },
                  ].map(({ key, label, desc }) => {
                    const types = esc.types || [];
                    return (
                      <FormControlLabel key={key}
                        sx={{ display: 'block', mb: 0.5 }}
                        control={<Switch size="small" checked={types.includes(key)}
                          onChange={(e) => {
                            const updated = e.target.checked
                              ? [...types, key]
                              : types.filter(t => t !== key);
                            updateSetting('escalation.types', updated);
                          }} />}
                        label={<Box><Typography variant="body2">{label}</Typography>
                          <Typography variant="caption" color="text.secondary">{desc}</Typography></Box>}
                      />
                    );
                  })}
              </CollapsibleCard>

              <CollapsibleCard id="tg.ai.escalation_auto_learn" title="Auto-Learn from Admin Replies">
                  <FormControlLabel
                    control={<Switch checked={esc.auto_learn !== false}
                      onChange={(e) => updateSetting('escalation.auto_learn', e.target.checked)} />}
                    label="Auto-learn from admin replies"
                  />
                  <Typography variant="caption" color="text.secondary" display="block">
                    When an admin replies to an escalation DM, the Q&amp;A is automatically stored in the
                    Knowledge Base for future auto-replies.
                  </Typography>
              </CollapsibleCard>
            </>
          );
        })()}

        {/* ══════════════════════════════════════════════════════════
            ANALYTICS
        ══════════════════════════════════════════════════════════ */}

        {/* ANALYTICS › Members Directory */}
        {cat === 'analytics' && subTab === 0 && (() => {
          return (
          <>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
              <Button size="small" variant="outlined" startIcon={<People fontSize="small" />}
                onClick={() => navigate(isOfficial ? `/groups/${groupId}/crm` : `/bot/${botId}/group/${groupId}/crm`)}
                sx={{ fontSize: '0.72rem' }}>
                Open CRM View
              </Button>
              <Button size="small" variant="outlined" startIcon={<FileDownload fontSize="small" />}
                onClick={exportMembersCSV} disabled={!members.length}
                sx={{ fontSize: '0.72rem' }}>
                Export CSV
              </Button>
            </Box>
            <>
              {/* Time range chips */}
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mb: 1.5 }}>
                {[
                  { key: 'all', label: 'All Time' },
                  { key: '30d', label: '30 Days' },
                  { key: '7d', label: '7 Days' },
                  { key: '1d', label: 'Today' },
                ].map(({ key, label }) => (
                  <Chip
                    key={key}
                    label={label}
                    size="small"
                    variant={membersTimeRange === key ? 'filled' : 'outlined'}
                    color={membersTimeRange === key ? 'primary' : 'default'}
                    onClick={() => { setMembersTimeRange(key); setMembersPage(1); }}
                    sx={{ cursor: 'pointer' }}
                  />
                ))}
              </Box>
              {/* Search and sort controls */}
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, mb: 2 }}>
                <TextField
                  size="small"
                  placeholder="Search name, @username, Telegram ID, wallet…"
                  sx={{ flex: '1 1 240px' }}
                  value={membersSearch}
                  onChange={(e) => { setMembersSearch(e.target.value); setMembersPage(1); }}
                />
                <FormControl size="small" sx={{ minWidth: 130 }}>
                  <InputLabel>Sort by</InputLabel>
                  <Select value={membersSort} label="Sort by" onChange={(e) => { setMembersSort(e.target.value); setMembersPage(1); }}>
                    <MenuItem value="xp">XP</MenuItem>
                    <MenuItem value="level">Level</MenuItem>
                    <MenuItem value="first_name">Name</MenuItem>
                    <MenuItem value="joined_at">Joined</MenuItem>
                    <MenuItem value="warnings">Warnings</MenuItem>
                    <MenuItem value="wallet_address">Wallet</MenuItem>
                  </Select>
                </FormControl>
              </Box>
            </>
            {isMobile ? (
              <Stack spacing={1.5}>
                {members.map((m) => {
                  const xpField = { '1d': 'xp_1d', '7d': 'xp_7d', '30d': 'xp_30d' }[membersTimeRange] || 'xp';
                  return (
                    <Box key={m.id} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1.5, p: 1.5 }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 0.75 }}>
                        <Typography variant="body2" fontWeight={600}>
                          {m.first_name}{m.username ? ` (@${m.username})` : ''}
                        </Typography>
                        <Chip label={m.role} size="small" variant="outlined" />
                      </Box>
                      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mb: 0.75 }}>
                        <Chip label={`XP ${(m[xpField] ?? 0).toLocaleString()}`} size="small" color="primary" variant="outlined" />
                        <Chip label={`Lv ${m.level}`} size="small" variant="outlined" />
                        {m.warnings > 0 && <Chip label={`${m.warnings} warn`} size="small" color="warning" />}
                        {m.is_verified
                          ? <Chip label="Verified" color="success" size="small" />
                          : <Chip label="Unverified" color="default" size="small" />}
                        {m.wallet_address && <Chip label="Wallet" color="success" size="small" />}
                      </Box>
                      {m.wallet_address && (
                        <Typography
                          variant="caption"
                          sx={{ fontFamily: 'monospace', color: 'primary.main', cursor: 'pointer' }}
                          onClick={() => navigator.clipboard.writeText(m.wallet_address)}
                        >
                          {m.wallet_address.length > 20
                            ? `${m.wallet_address.slice(0, 10)}…${m.wallet_address.slice(-8)}`
                            : m.wallet_address}
                        </Typography>
                      )}
                    </Box>
                  );
                })}
              </Stack>
            ) : (
              <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider', overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>User</TableCell>
                      <TableCell align="right">
                        {membersTimeRange === '1d' ? 'XP (Today)' : membersTimeRange === '7d' ? 'XP (7d)' : membersTimeRange === '30d' ? 'XP (30d)' : 'XP'}
                      </TableCell>
                      <TableCell align="right">Level</TableCell>
                      <TableCell align="right">Warnings</TableCell>
                      <TableCell>Role</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Wallet</TableCell>
                      <TableCell>Wallet Address</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {members.map((m) => {
                      const xpField = { '1d': 'xp_1d', '7d': 'xp_7d', '30d': 'xp_30d' }[membersTimeRange] || 'xp';
                      return (
                        <TableRow key={m.id} hover>
                          <TableCell>
                            <Typography variant="body2" fontWeight={500}>
                              {m.first_name}{m.username ? ` (@${m.username})` : ''}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">{(m[xpField] ?? 0).toLocaleString()}</TableCell>
                          <TableCell align="right">{m.level}</TableCell>
                          <TableCell align="right">{m.warnings}</TableCell>
                          <TableCell><Chip label={m.role} size="small" variant="outlined" /></TableCell>
                          <TableCell>
                            {m.is_verified
                              ? <Chip label="Verified" color="success" size="small" />
                              : <Chip label="Unverified" color="default" size="small" />}
                          </TableCell>
                          <TableCell>
                            {m.wallet_address
                              ? <Chip label="Yes" color="success" size="small" />
                              : <Chip label="No" color="default" size="small" />}
                          </TableCell>
                          <TableCell sx={{ maxWidth: 180 }}>
                            {m.wallet_address ? (
                              <Tooltip title={m.wallet_address} arrow>
                                <Typography
                                  variant="body2"
                                  sx={{
                                    fontFamily: 'monospace', fontSize: '0.75rem',
                                    overflow: 'hidden', textOverflow: 'ellipsis',
                                    whiteSpace: 'nowrap', cursor: 'pointer', color: 'primary.main',
                                  }}
                                  onClick={() => navigator.clipboard.writeText(m.wallet_address)}
                                >
                                  {m.wallet_address.length > 16
                                    ? `${m.wallet_address.slice(0, 8)}…${m.wallet_address.slice(-6)}`
                                    : m.wallet_address}
                                </Typography>
                              </Tooltip>
                            ) : (
                              <Typography variant="body2" color="text.disabled">—</Typography>
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
            {membersPages > 1 && (
              <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
                <Pagination count={membersPages} page={membersPage}
                  onChange={(_, p) => setMembersPage(p)} color="primary" />
              </Box>
            )}
          </>
          );
        })()}

        {/* ANALYTICS › Leaderboard */}
        {cat === 'analytics' && subTab === leaderboardSubTabIdx && (() => {
          const lbXpField = { '1d': 'xp_1d', '7d': 'xp_7d', '30d': 'xp_30d' }[leaderboardTimeRange] || 'xp';
          return (
          <>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1, mb: 1.5 }}>
              <Box sx={{ minWidth: 0 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <EmojiEvents color="primary" />
                  <Typography variant="h6" fontWeight={600}>XP Leaderboard</Typography>
                </Box>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>Top members ranked by XP</Typography>
              </Box>
              <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', alignItems: 'center' }}>
                {[
                  { key: 'all', label: 'All Time' },
                  { key: '30d', label: '30 Days' },
                  { key: '7d', label: '7 Days' },
                  { key: '1d', label: 'Today' },
                ].map(({ key, label }) => (
                  <Chip
                    key={key}
                    label={label}
                    size="small"
                    variant={leaderboardTimeRange === key ? 'filled' : 'outlined'}
                    color={leaderboardTimeRange === key ? 'primary' : 'default'}
                    onClick={() => setLeaderboardTimeRange(key)}
                    sx={{ cursor: 'pointer' }}
                  />
                ))}
                <Chip
                  label="Has Wallet"
                  size="small"
                  variant={leaderboardWalletOnly ? 'filled' : 'outlined'}
                  color={leaderboardWalletOnly ? 'success' : 'default'}
                  onClick={() => setLeaderboardWalletOnly(v => !v)}
                  sx={{ cursor: 'pointer' }}
                />
                <Button size="small" variant="outlined" startIcon={<FileDownload fontSize="small" />}
                  onClick={exportLeaderboardCSV} disabled={!leaderboard.length}
                  sx={{ fontSize: '0.72rem' }}>
                  Export CSV
                </Button>
              </Box>
            </Box>
            <TextField
              size="small" fullWidth sx={{ mb: 1.5 }}
              placeholder="Search name, @username, Telegram ID, wallet…"
              value={leaderboardSearch}
              onChange={(e) => setLeaderboardSearch(e.target.value)}
              InputProps={{ startAdornment: (<InputAdornment position="start"><Search fontSize="small" /></InputAdornment>) }}
            />
            {leaderboardTimeRange !== 'all' && (
              <Typography variant="caption" color="text.secondary" display="block" mb={1.5}>
                Showing XP earned in the last {leaderboardTimeRange === '1d' ? '24 hours' : leaderboardTimeRange === '7d' ? '7 days' : '30 days'}.
              </Typography>
            )}
            {leaderboardLoading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}><CircularProgress /></Box>
            ) : leaderboard.length === 0 ? (
              <Typography variant="body2" color="text.secondary" py={2} textAlign="center">
                No members with XP yet. Members earn XP by sending messages and using commands.
              </Typography>
            ) : isMobile ? (
              <Stack spacing={1.5}>
                {leaderboard.map((m, idx) => (
                  <Box key={m.id} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1.5, p: 1.5 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                      <Typography variant="body2" fontWeight={idx < 3 ? 800 : 600}
                        color={idx === 0 ? '#FFD700' : idx === 1 ? '#C0C0C0' : idx === 2 ? '#CD7F32' : 'text.secondary'}>
                        {idx < 3 ? ['🥇', '🥈', '🥉'][idx] : `#${idx + 1}`}
                      </Typography>
                      <Typography variant="body2" fontWeight={idx < 3 ? 700 : 400} sx={{ flex: 1 }} noWrap>
                        {m.first_name}{m.username ? ` (@${m.username})` : ''}
                      </Typography>
                      <Typography variant="body2" fontWeight={700} color="primary.main">
                        {(m[lbXpField] ?? 0).toLocaleString()} XP
                      </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                      <Chip label={`Lv ${m.level}`} size="small" variant="outlined" />
                      <Chip label={m.role} size="small" variant="outlined" />
                      {m.wallet_address && (
                        <Chip label="Wallet" size="small" color="success"
                          onClick={() => navigator.clipboard.writeText(m.wallet_address)} />
                      )}
                    </Box>
                  </Box>
                ))}
              </Stack>
            ) : (
              <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider', overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell align="center">#</TableCell>
                      <TableCell>User</TableCell>
                      <TableCell align="right">
                        {leaderboardTimeRange === '1d' ? 'XP (Today)' : leaderboardTimeRange === '7d' ? 'XP (7d)' : leaderboardTimeRange === '30d' ? 'XP (30d)' : 'XP'}
                      </TableCell>
                      <TableCell align="right">Level</TableCell>
                      <TableCell>Role</TableCell>
                      <TableCell>Wallet Address</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {leaderboard.map((m, idx) => (
                      <TableRow key={m.id} hover>
                        <TableCell align="center">
                          <Typography
                            variant="body2"
                            fontWeight={idx < 3 ? 800 : 400}
                            color={idx === 0 ? '#FFD700' : idx === 1 ? '#C0C0C0' : idx === 2 ? '#CD7F32' : 'text.primary'}
                          >
                            {idx < 3 ? ['🥇', '🥈', '🥉'][idx] : idx + 1}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" fontWeight={idx < 3 ? 700 : 400}>
                            {m.first_name}{m.username ? ` (@${m.username})` : ''}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="body2" fontWeight={600} color="primary.main">
                            {(m[lbXpField] ?? 0).toLocaleString()}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">{m.level}</TableCell>
                        <TableCell><Chip label={m.role} size="small" variant="outlined" /></TableCell>
                        <TableCell sx={{ maxWidth: 180 }}>
                          {m.wallet_address ? (
                            <Tooltip title={m.wallet_address} arrow>
                              <Typography
                                variant="body2"
                                sx={{
                                  fontFamily: 'monospace', fontSize: '0.75rem',
                                  overflow: 'hidden', textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap', cursor: 'pointer', color: 'primary.main',
                                }}
                                onClick={() => navigator.clipboard.writeText(m.wallet_address)}
                              >
                                {m.wallet_address.length > 16
                                  ? `${m.wallet_address.slice(0, 8)}…${m.wallet_address.slice(-6)}`
                                  : m.wallet_address}
                              </Typography>
                            </Tooltip>
                          ) : (
                            <Typography variant="body2" color="text.disabled">—</Typography>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </>
          );
        })()}

        {/* ANALYTICS › Audit Log / Mod Log */}
        {cat === 'analytics' && subTab === auditLogSubTabIdx && (
          <>
            <Typography variant="body2" color="text.secondary" mb={1.5}>
              {isOfficial
                ? 'Moderation actions (bans, kicks, mutes, warns, purges) logged by @telegizer_bot in this group.'
                : 'Moderation actions (bans, kicks, mutes, warns, purges) logged by your bot in this group.'}
            </Typography>
            <TextField
              size="small" fullWidth sx={{ mb: 1.5 }}
              placeholder="Search target, moderator, reason, action, message…"
              value={auditSearch}
              onChange={(e) => { setAuditSearch(e.target.value); setAuditPage(1); }}
              InputProps={{ startAdornment: (<InputAdornment position="start"><Search fontSize="small" /></InputAdornment>) }}
            />
            {auditLogs.length === 0 ? (
              <Alert severity="info" icon={false}>
                No moderation events recorded yet. Events appear here after admins use commands like /ban, /kick, /mute, or /warn.
              </Alert>
            ) : isMobile ? (
              <Stack spacing={1.5}>
                {auditLogs.map((log) => {
                  const isExpanded = expandedLogId === log.id;
                  const linkType = classifyReason(log.reason);
                  const shortLabel = categorizeReason(log.reason);
                  const msgPreviewRaw = getMessagePreview(log);
                  return (
                    <Box key={log.id}
                      onClick={() => setExpandedLogId(isExpanded ? null : log.id)}
                      sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1.5, p: 1.5, cursor: 'pointer' }}
                    >
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
                        <Chip label={log.action_type} color={ACTION_COLORS[log.action_type] || 'default'} size="small" sx={{ height: 20, fontSize: '0.68rem' }} />
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }} onClick={(e) => e.stopPropagation()}>
                          <Typography variant="caption" color="text.secondary">
                            {fmtTs(log.timestamp)}
                          </Typography>
                          <ModerationActions
                            botId={botId} groupId={groupId}
                            userId={log.target_user_id} username={log.target_username}
                            onDone={() => { fetchAuditLogs(auditPage); fetchWarnings({ page: 1 }); }}
                          />
                        </Box>
                      </Box>
                      <Typography variant="caption" display="block">
                        <strong>Target:</strong> {log.target_username ? `@${log.target_username}` : log.target_user_id || '—'}
                        {' · '}<strong>By:</strong> {log.moderator_username ? `@${log.moderator_username}` : log.moderator_id || '—'}
                      </Typography>
                      {shortLabel && <Typography variant="caption" color="text.secondary" display="block">{shortLabel}</Typography>}
                      {isExpanded && (
                        <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid', borderColor: 'divider' }}>
                          <Stack spacing={0.5}>
                            {log.reason && (
                              <Box>
                                <Typography variant="caption" fontWeight={700} color="text.secondary" display="block">Full Reason</Typography>
                                <Typography variant="caption">{log.reason}</Typography>
                              </Box>
                            )}
                            {msgPreviewRaw && (
                              <Box>
                                <Typography variant="caption" fontWeight={700} color="text.secondary" display="block">Removed Message</Typography>
                                <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{msgPreviewRaw}</Typography>
                              </Box>
                            )}
                            {linkType && (
                              <Typography variant="caption" color="text.disabled">Link type: <strong>{linkType.label}</strong></Typography>
                            )}
                          </Stack>
                        </Box>
                      )}
                    </Box>
                  );
                })}
              </Stack>
            ) : (
            <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider', overflowX: 'auto' }}>
              <Table size="small" sx={{ tableLayout: 'fixed', minWidth: 640 }}>
                <TableHead>
                  <TableRow sx={{ '& th': { py: 0.75, fontSize: '0.75rem', fontWeight: 700, whiteSpace: 'nowrap' } }}>
                    <TableCell sx={{ width: 90 }}>Action</TableCell>
                    <TableCell sx={{ width: 110 }}>Target</TableCell>
                    <TableCell sx={{ width: 110 }}>Moderator</TableCell>
                    <TableCell sx={{ width: 130 }}>Reason</TableCell>
                    <TableCell>Msg Preview</TableCell>
                    <TableCell sx={{ width: 120 }}>Time</TableCell>
                    <TableCell sx={{ width: 56 }} align="right">Act</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {auditLogs.map((log) => {
                    const isExpanded = expandedLogId === log.id;
                    const linkType = classifyReason(log.reason);
                    const shortLabel = categorizeReason(log.reason);
                    const msgPreviewRaw = getMessagePreview(log);
                    const msgPreview = formatMsgPreview(msgPreviewRaw);
                    const cellSx = { py: 0.5, overflow: 'hidden' };
                    return (
                      <React.Fragment key={log.id}>
                        <TableRow
                          hover
                          onClick={() => setExpandedLogId(isExpanded ? null : log.id)}
                          sx={{ cursor: 'pointer', '& td': { borderBottom: isExpanded ? 'none' : undefined } }}
                        >
                          <TableCell sx={cellSx}>
                            <Chip label={log.action_type} color={ACTION_COLORS[log.action_type] || 'default'} size="small" sx={{ height: 20, fontSize: '0.68rem' }} />
                          </TableCell>
                          <TableCell sx={{ ...cellSx, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            <Typography variant="caption" noWrap>
                              {log.target_username ? `@${log.target_username}` : log.target_user_id || '—'}
                            </Typography>
                          </TableCell>
                          <TableCell sx={{ ...cellSx, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            <Typography variant="caption" noWrap>
                              {log.moderator_username ? `@${log.moderator_username}` : log.moderator_id || '—'}
                            </Typography>
                          </TableCell>
                          <TableCell sx={cellSx}>
                            <Typography variant="caption" color="text.secondary" noWrap title={log.reason || ''}>
                              {shortLabel}
                            </Typography>
                          </TableCell>
                          <TableCell sx={{ ...cellSx, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            <Typography variant="caption" color="text.disabled" noWrap title={msgPreviewRaw || ''}>
                              {msgPreview || '—'}
                            </Typography>
                          </TableCell>
                          <TableCell sx={cellSx}>
                            <Typography variant="caption" color="text.secondary" noWrap>
                              {fmtTs(log.timestamp)}
                            </Typography>
                          </TableCell>
                          <TableCell sx={cellSx} align="right" onClick={(e) => e.stopPropagation()}>
                            <ModerationActions
                              botId={botId} groupId={groupId}
                              userId={log.target_user_id} username={log.target_username}
                              onDone={() => { fetchAuditLogs(auditPage); fetchWarnings({ page: 1 }); }}
                            />
                          </TableCell>
                        </TableRow>
                        {isExpanded && (
                          <TableRow>
                            <TableCell colSpan={7} sx={{ py: 1.5, px: 2.5, bgcolor: 'rgba(255,255,255,0.025)' }}>
                              <Stack spacing={0.75}>
                                {log.reason && (
                                  <Box>
                                    <Typography variant="caption" fontWeight={700} color="text.secondary" display="block">Full Reason</Typography>
                                    <Typography variant="caption" color="text.primary">{log.reason}</Typography>
                                  </Box>
                                )}
                                {msgPreviewRaw && (
                                  <Box>
                                    <Typography variant="caption" fontWeight={700} color="text.secondary" display="block">Removed Message</Typography>
                                    <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{msgPreviewRaw}</Typography>
                                  </Box>
                                )}
                                {linkType && (
                                  <Typography variant="caption" color="text.disabled">
                                    Link type: <strong>{linkType.label}</strong>
                                    {linkType.label === 'Telegizer link' && ' — Telegizer invite links are never deleted by AutoMod.'}
                                  </Typography>
                                )}
                              </Stack>
                            </TableCell>
                          </TableRow>
                        )}
                      </React.Fragment>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
            )}
            {auditTotal > 1 && (
              <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
                <Pagination count={auditTotal} page={auditPage}
                  onChange={(_, p) => setAuditPage(p)} color="primary" />
              </Box>
            )}
          </>
        )}

        {/* ANALYTICS › Warnings */}
        {cat === 'analytics' && subTab === warningsSubTabIdx && (() => {
          // Search + pagination are server-side now, so the loaded rows ARE the
          // result set (no client-side cap that made the count stick at 200).
          const filteredWarnings = warnings;
          return (
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <WarningIcon color="warning" />
                  <Typography variant="h6" fontWeight={600}>Active Warnings</Typography>
                  <Chip label={warningsActiveTotal} size="small" color="warning" variant="outlined" />
                </Box>
                <Button size="small" onClick={() => fetchWarnings({ page: 1 })} disabled={warningsLoading}>Refresh</Button>
              </Box>
              <Typography variant="body2" color="text.secondary" mb={1.5}>
                Active warnings issued by admins via <code>/warn</code>. Click any row to see full details.
              </Typography>
              <TextField
                size="small" fullWidth
                placeholder="Search member id, name, username, reason, moderator, message…"
                value={warningsSearch}
                onChange={(e) => setWarningsSearch(e.target.value)}
                sx={{ mb: 1.5 }}
              />
              {warningsLoading && warnings.length === 0 ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}><CircularProgress size={24} /></Box>
              ) : warnings.length === 0 && !warningsSearch.trim() ? (
                <Alert severity="success" icon={<CheckCircle />}>No active warnings in this group.</Alert>
              ) : filteredWarnings.length === 0 ? (
                <Typography variant="body2" color="text.secondary">No warnings match your search.</Typography>
              ) : isMobile ? (
                <Stack spacing={1.5}>
                  {filteredWarnings.map((warning) => {
                    const isExpanded = expandedWarnId === warning.id;
                    const shortLabel = categorizeReason(warning.reason);
                    const warnMsgRaw = warning.message_text || null;
                    const warnMsgPreview = formatMsgPreview(warnMsgRaw);
                    return (
                      <Box key={warning.id}
                        onClick={() => setExpandedWarnId(isExpanded ? null : warning.id)}
                        sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1.5, p: 1.5, cursor: 'pointer' }}
                      >
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
                          <Box sx={{ minWidth: 0 }}>
                            <Typography variant="body2" fontWeight={600} noWrap>
                              {warning.full_name
                                || (warning.resolved_username ? `@${warning.resolved_username}` : null)
                                || (warning.target_username ? `@${warning.target_username}` : warning.target_user_id)}
                            </Typography>
                            {(warning.full_name || warning.resolved_username) && (
                              <Typography variant="caption" color="text.disabled" noWrap>
                                {warning.resolved_username ? `@${warning.resolved_username} · ` : ''}id {warning.target_user_id}
                              </Typography>
                            )}
                          </Box>
                          <Box sx={{ display: 'flex', alignItems: 'center' }} onClick={(e) => e.stopPropagation()}>
                            <ModerationActions
                              botId={botId} groupId={groupId}
                              userId={warning.target_user_id}
                              username={warning.resolved_username || warning.target_username}
                              onDone={() => fetchWarnings({ page: 1 })}
                            />
                            <Tooltip title="Remove warning">
                              <IconButton size="small" color="error" onClick={(e) => { e.stopPropagation(); handleRemoveWarning(warning.id); }}>
                                <Delete sx={{ fontSize: 16 }} />
                              </IconButton>
                            </Tooltip>
                          </Box>
                        </Box>
                        {shortLabel && <Typography variant="caption" color="text.secondary" display="block">{shortLabel}</Typography>}
                        {warnMsgPreview && <Typography variant="caption" color="text.disabled" display="block" noWrap>{warnMsgPreview}</Typography>}
                        <Typography variant="caption" color="text.disabled" display="block" mt={0.25}>
                          By {warning.moderator_username ? `@${warning.moderator_username}` : warning.moderator_user_id}
                          {' · '}{fmtTs(warning.created_at)}
                        </Typography>
                        {isExpanded && (
                          <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid', borderColor: 'divider' }}>
                            <Stack spacing={0.5}>
                              {warning.reason && (
                                <Box>
                                  <Typography variant="caption" fontWeight={700} color="text.secondary" display="block">Full Reason</Typography>
                                  <Typography variant="caption">{warning.reason}</Typography>
                                </Box>
                              )}
                              {warnMsgRaw && (
                                <Box>
                                  <Typography variant="caption" fontWeight={700} color="text.secondary" display="block">Warned Message</Typography>
                                  <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{warnMsgRaw}</Typography>
                                </Box>
                              )}
                            </Stack>
                          </Box>
                        )}
                      </Box>
                    );
                  })}
                </Stack>
              ) : (
                <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider', overflowX: 'auto' }}>
                  <Table size="small" sx={{ tableLayout: 'fixed', minWidth: 500 }}>
                    <TableHead>
                      <TableRow sx={{ '& th': { py: 0.75, fontSize: '0.75rem', fontWeight: 700, whiteSpace: 'nowrap' } }}>
                        <TableCell sx={{ width: 130 }}>Member</TableCell>
                        <TableCell sx={{ width: 110 }}>Reason</TableCell>
                        <TableCell>Msg Preview</TableCell>
                        <TableCell sx={{ width: 120 }}>Issued By</TableCell>
                        <TableCell sx={{ width: 110 }}>Date</TableCell>
                        <TableCell sx={{ width: 90 }} align="center">Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {filteredWarnings.map((warning) => {
                        const isExpanded = expandedWarnId === warning.id;
                        const shortLabel = categorizeReason(warning.reason);
                        const warnMsgRaw     = warning.message_text || null;
                        const warnMsgPreview = formatMsgPreview(warnMsgRaw);
                        const cellSx = { py: 0.5, overflow: 'hidden' };
                        return (
                          <React.Fragment key={warning.id}>
                            <TableRow
                              hover
                              onClick={() => setExpandedWarnId(isExpanded ? null : warning.id)}
                              sx={{ cursor: 'pointer', '& td': { borderBottom: isExpanded ? 'none' : undefined } }}
                            >
                              <TableCell sx={cellSx}>
                                <Typography variant="caption" fontWeight={600} noWrap title={warning.target_user_id || ''}>
                                  {warning.full_name
                                    || (warning.resolved_username ? `@${warning.resolved_username}` : null)
                                    || (warning.target_username ? `@${warning.target_username}` : warning.target_user_id)}
                                </Typography>
                                {(warning.full_name || warning.resolved_username) && (
                                  <Typography variant="caption" color="text.disabled" display="block" noWrap>
                                    {warning.resolved_username ? `@${warning.resolved_username} · ` : ''}id {warning.target_user_id}
                                  </Typography>
                                )}
                              </TableCell>
                              <TableCell sx={cellSx}>
                                <Typography variant="caption" color="text.secondary" noWrap title={warning.reason || ''}>
                                  {shortLabel}
                                </Typography>
                              </TableCell>
                              <TableCell sx={{ ...cellSx, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                <Typography variant="caption" color="text.disabled" noWrap title={warnMsgRaw || ''}>
                                  {warnMsgPreview || '—'}
                                </Typography>
                              </TableCell>
                              <TableCell sx={cellSx}>
                                <Typography variant="caption" noWrap>
                                  {warning.moderator_username ? `@${warning.moderator_username}` : warning.moderator_user_id}
                                </Typography>
                              </TableCell>
                              <TableCell sx={cellSx}>
                                <Typography variant="caption" color="text.secondary" noWrap>
                                  {fmtTs(warning.created_at)}
                                </Typography>
                              </TableCell>
                              <TableCell sx={cellSx} align="center" onClick={(e) => e.stopPropagation()}>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                  <ModerationActions
                                    botId={botId} groupId={groupId}
                                    userId={warning.target_user_id}
                                    username={warning.resolved_username || warning.target_username}
                                    onDone={() => fetchWarnings({ page: 1 })}
                                  />
                                  <Tooltip title="Remove warning">
                                    <IconButton size="small" color="error" onClick={(e) => { e.stopPropagation(); handleRemoveWarning(warning.id); }}>
                                      <Delete sx={{ fontSize: 16 }} />
                                    </IconButton>
                                  </Tooltip>
                                </Box>
                              </TableCell>
                            </TableRow>
                            {isExpanded && (
                              <TableRow>
                                <TableCell colSpan={6} sx={{ py: 1.5, px: 2.5, bgcolor: 'rgba(255,255,255,0.025)' }}>
                                  <Stack spacing={0.75}>
                                    {warning.reason && (
                                      <Box>
                                        <Typography variant="caption" fontWeight={700} color="text.secondary" display="block">Full Reason</Typography>
                                        <Typography variant="caption" color="text.primary">{warning.reason}</Typography>
                                      </Box>
                                    )}
                                    {warnMsgRaw && (
                                      <Box>
                                        <Typography variant="caption" fontWeight={700} color="text.secondary" display="block">Warned Message</Typography>
                                        <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{warnMsgRaw}</Typography>
                                      </Box>
                                    )}
                                    <Typography variant="caption" color="text.disabled">
                                      Issued by: {warning.moderator_username ? `@${warning.moderator_username}` : warning.moderator_user_id}
                                      {' · '}{fmtTs(warning.created_at)}
                                    </Typography>
                                  </Stack>
                                </TableCell>
                              </TableRow>
                            )}
                          </React.Fragment>
                        );
                      })}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
              {warnings.length > 0 && warnings.length < warningsTotal && (
                <Box sx={{ display: 'flex', justifyContent: 'center', mt: 1.5 }}>
                  <Button size="small" variant="outlined" disabled={warningsLoading}
                    onClick={() => fetchWarnings({ page: warningsPage + 1 })}>
                    {warningsLoading ? 'Loading…' : `Load more (${warnings.length} of ${warningsTotal})`}
                  </Button>
                </Box>
              )}
            </CardContent>
          </Card>
          );
        })()}


        {/* ANALYTICS › Digest */}
        {cat === 'analytics' && subTab === digestSubTabIdx && (
          digestLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}><CircularProgress /></Box>
          ) : (
            <>
              <CollapsibleCard id="tg.analytics.report_digest" title="Telegram Report Digest" sx={{ mb: 2 }}>
                  <Typography variant="body2" color="text.secondary" mb={3}>
                    Automatically send a summary report to this Telegram group on your chosen schedule.
                    The report includes spam removed, members warned/banned, scheduled posts sent, polls created, and growth stats.
                  </Typography>

                  <Grid container spacing={2} mb={3}>
                    {[
                      { key: 'daily',   label: 'Daily Report',   desc: 'Sent every ~24 hours' },
                      { key: 'weekly',  label: 'Weekly Report',  desc: 'Sent every ~7 days' },
                      { key: 'monthly', label: 'Monthly Report', desc: 'Sent every ~30 days' },
                    ].map(({ key, label, desc }) => (
                      <Grid item xs={12} sm={4} key={key}>
                        <Card
                          variant="outlined"
                          sx={{
                            p: 2,
                            borderColor: digestConfig[key] ? 'primary.main' : 'divider',
                            bgcolor: digestConfig[key] ? 'rgba(33,150,243,0.05)' : 'transparent',
                            cursor: 'pointer',
                          }}
                          onClick={() => setDigestConfig((prev) => ({ ...prev, [key]: !prev[key] }))}
                        >
                          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Box>
                              <Typography variant="body2" fontWeight={700}>{label}</Typography>
                              <Typography variant="caption" color="text.secondary">{desc}</Typography>
                            </Box>
                            <Switch
                              checked={!!digestConfig[key]}
                              onChange={(e) => {
                                e.stopPropagation();
                                setDigestConfig((prev) => ({ ...prev, [key]: e.target.checked }));
                              }}
                              size="small"
                            />
                          </Box>
                          {digestConfig[`last_${key}`] && (
                            <Typography variant="caption" color="text.disabled" display="block" mt={0.5}>
                              Last sent: {fmtTs(digestConfig[`last_${key}`])}
                            </Typography>
                          )}
                        </Card>
                      </Grid>
                    ))}
                  </Grid>

                  <Button
                    variant="contained"
                    startIcon={digestSaving ? <CircularProgress size={16} color="inherit" /> : <Save />}
                    onClick={handleSaveDigest}
                    disabled={digestSaving}
                    sx={{ mr: 2 }}
                  >
                    Save Digest Settings
                  </Button>
              </CollapsibleCard>

              {/* Digest Recipients — shown for both official-bot and custom-bot groups */}
              <CollapsibleCard id="tg.analytics.report_recipients" title="Report Recipients" sx={{ mb: 2 }}>
                    <Typography variant="body2" color="text.secondary" mb={2}>
                      Choose who receives the digest report. Recipients marked ⚠ have not yet started @telegizer_bot and cannot receive private DMs.
                    </Typography>

                    <FormControlLabel
                      control={<Switch checked={!!(digestConfig.recipients?.send_to_group ?? true)}
                        onChange={(e) => setDigestConfig(prev => ({
                          ...prev,
                          recipients: { ...(prev.recipients || {}), send_to_group: e.target.checked },
                        }))} />}
                      label="Send report to the group"
                    />

                    {(digestConfig.recipients?.send_to_group ?? true) && (
                      <TextField fullWidth size="small" label="Topic ID (blank = main chat)" sx={{ mt: 1, mb: 2 }}
                        type="number"
                        value={digestConfig.recipients?.group_topic_id || ''}
                        onChange={(e) => setDigestConfig(prev => ({
                          ...prev,
                          recipients: { ...(prev.recipients || {}), group_topic_id: e.target.value ? parseInt(e.target.value) : null },
                        }))}
                        helperText="Send to a specific forum topic thread inside the group" />
                    )}

                    <Divider sx={{ my: 2 }} />

                    <FormControlLabel
                      control={<Switch checked={!!(digestConfig.recipients?.owner_dm)}
                        onChange={(e) => setDigestConfig(prev => ({
                          ...prev,
                          recipients: { ...(prev.recipients || {}), owner_dm: e.target.checked },
                        }))} />}
                      label="Send private DM to account owner (must have started @telegizer_bot)"
                    />

                    <Divider sx={{ my: 2 }} />

                    <Typography variant="subtitle2" fontWeight={600} mb={1}>Send private DM to selected admins</Typography>
                    <Typography variant="caption" color="text.secondary" display="block" mb={1.5}>
                      Only admins who have started @telegizer_bot can receive DMs.
                    </Typography>

                    {adminsLoading ? (
                      <CircularProgress size={20} />
                    ) : groupAdmins.length === 0 ? (
                      <Typography variant="caption" color="text.secondary">No admins loaded. Switch to Reports tab to load them.</Typography>
                    ) : (
                      <Stack spacing={0.75}>
                        {groupAdmins.map((admin) => {
                          const selIds = digestConfig.recipients?.selected_admin_ids || [];
                          const selected = selIds.includes(admin.user_id);
                          return (
                            <Box key={admin.user_id} sx={{
                              display: 'flex', alignItems: 'center', gap: 1,
                              p: 1, border: '1px solid', borderRadius: 1.5,
                              borderColor: selected ? 'primary.main' : 'divider',
                              opacity: admin.can_dm ? 1 : 0.65,
                              cursor: admin.can_dm ? 'pointer' : 'default',
                              minWidth: 0, overflow: 'hidden',
                            }}
                              onClick={() => {
                                if (!admin.can_dm) return;
                                setDigestConfig(prev => {
                                  const cur = prev.recipients?.selected_admin_ids || [];
                                  return {
                                    ...prev,
                                    recipients: {
                                      ...(prev.recipients || {}),
                                      selected_admin_ids: selected
                                        ? cur.filter(id => id !== admin.user_id)
                                        : [...cur, admin.user_id],
                                    },
                                  };
                                });
                              }}
                            >
                              <Switch size="small" checked={selected} disabled={!admin.can_dm} onChange={() => {}} sx={{ flexShrink: 0 }} />
                              <Typography variant="body2" sx={{ flexGrow: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {admin.first_name}{admin.username ? ` (@${admin.username})` : ''}
                              </Typography>
                              <Box sx={{ flexShrink: 0, width: { xs: 108, sm: 132 }, display: 'flex', justifyContent: 'flex-end' }}>
                                {admin.can_dm
                                  ? <Chip label="✓ Can receive DM" color="success" size="small" sx={{ maxWidth: '100%', '& .MuiChip-label': { px: 0.75, fontSize: '0.68rem' } }} />
                                  : <Tooltip title="Ask this admin to open @telegizer_bot and press Start.">
                                      <Chip label="⚠ Must start bot" color="warning" size="small" sx={{ maxWidth: '100%', '& .MuiChip-label': { px: 0.75, fontSize: '0.68rem' } }} />
                                    </Tooltip>
                                }
                              </Box>
                            </Box>
                          );
                        })}
                      </Stack>
                    )}

                    <Box sx={{ mt: 2 }}>
                      <Button
                        variant="contained"
                        size="small"
                        startIcon={digestSaving ? <CircularProgress size={14} color="inherit" /> : <Save />}
                        onClick={handleSaveDigest}
                        disabled={digestSaving}
                      >
                        Save Recipient Settings
                      </Button>
                    </Box>
              </CollapsibleCard>

              {/* AI Summary — official-bot groups only */}
              {isOfficial && (
                <Card sx={{ mb: 2, border: '1px solid', borderColor: settingsData?.assistant?.ai_digest_enabled ? 'secondary.main' : 'divider', bgcolor: settingsData?.assistant?.ai_digest_enabled ? 'rgba(124,58,237,0.06)' : 'transparent' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                      <Box>
                        <Typography variant="subtitle1" fontWeight={600}>🤖 AI Summary (Beta)</Typography>
                        <Typography variant="body2" color="text.secondary" mt={0.5}>
                          Append an AI-generated plain-English summary to your digest.
                          Uses your group's AI API key — <strong>zero cost to you</strong>.
                        </Typography>
                      </Box>
                      <Switch
                        checked={!!(settingsData?.assistant?.ai_digest_enabled)}
                        onChange={(e) => updateSetting('assistant.ai_digest_enabled', e.target.checked)}
                      />
                    </Box>

                    {settingsData?.assistant?.ai_digest_enabled && (
                      <Alert severity="info" sx={{ mt: 1.5, fontSize: '0.82rem' }}>
                        <strong>Requirements:</strong> You must have an AI API key configured under{' '}
                        <strong>AI &amp; Integrations → Knowledge Base</strong>. Messages in this group will be
                        buffered for up to 48 hours for summarization. No message content is sent to our servers —
                        only to your own API provider.
                      </Alert>
                    )}

                    {settingsData?.assistant?.ai_digest_enabled && (
                      <Box sx={{ mt: 2 }}>
                        <Button
                          variant="outlined"
                          size="small"
                          startIcon={saving ? <CircularProgress size={14} color="inherit" /> : null}
                          onClick={handleSave}
                          disabled={saving}
                        >
                          Save AI Setting
                        </Button>
                      </Box>
                    )}
                  </CardContent>
                </Card>
              )}

              <CollapsibleCard id="tg.analytics.send_report_now" title="Send Report Now">
                  <Typography variant="body2" color="text.secondary" mb={2}>
                    Immediately send a report to all configured recipients.
                    Useful for checking the setup or sharing a snapshot with your community.
                  </Typography>
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                    {[
                      { key: 'daily',   label: 'Send Daily Report' },
                      { key: 'weekly',  label: 'Send Weekly Report' },
                      { key: 'monthly', label: 'Send Monthly Report' },
                    ].map(({ key, label }) => (
                      <Button
                        key={key}
                        variant="outlined"
                        startIcon={digestSending === key
                          ? <CircularProgress size={16} color="inherit" />
                          : <Send fontSize="small" />
                        }
                        disabled={!!digestSending}
                        onClick={() => handleSendNow(key)}
                      >
                        {label}
                      </Button>
                    ))}
                  </Stack>

                  <Alert severity="info" sx={{ mt: 2 }} icon={false}>
                    <Typography variant="caption">
                      The bot must be active and present in the group as an admin to send reports.
                      Admins who have not started @telegizer_bot will be silently skipped.
                    </Typography>
                  </Alert>
              </CollapsibleCard>
            </>
          )
        )}

        {/* ── AI Activity (reporting layer) ── */}
        {cat === 'analytics' && subTab === aiActivitySubTabIdx && (
          aiActivityLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress /></Box>
          ) : (
            <>
              {/* AI Status panel */}
              {aiStatus && (
                <CollapsibleCard id="tg.analytics.ai_status" title="🤖 AI Status" sx={{ mb: 2 }}>
                    <Grid container spacing={1.5}>
                      {[
                        { label: 'Smart Moderation', value: aiStatus.smart_moderation, good: 'enabled' },
                        { label: 'AI Integrations', value: aiStatus.ai_integrations, good: 'connected' },
                        { label: 'Knowledge Base', value: aiStatus.knowledge_base, good: 'configured' },
                        { label: 'OpenAI Provider', value: aiStatus.openai_provider, good: 'connected' },
                      ].map(({ label, value, good }) => {
                        const target = aiStatusTargets[label];
                        return (
                        <Grid item xs={6} sm={3} key={label}>
                          <Tooltip title={target ? `Configure → ${currentCat && CATEGORIES.find(c => c.id === target.cat)?.label}` : ''}>
                            <Box
                              onClick={() => goToTarget(target)}
                              sx={{
                                cursor: 'pointer', borderRadius: 1.5, p: 1, m: -1,
                                transition: 'background 0.15s ease',
                                '&:hover': { bgcolor: 'rgba(255,255,255,0.06)' },
                              }}
                            >
                              <Typography variant="caption" color="text.secondary">{label} ›</Typography>
                              <Box mt={0.5}>
                                <Chip
                                  size="small"
                                  label={(value || 'unknown').replace(/_/g, ' ')}
                                  color={value === good ? 'success' : 'default'}
                                  variant={value === good ? 'filled' : 'outlined'}
                                  sx={{ textTransform: 'capitalize', fontWeight: 600, cursor: 'pointer' }}
                                />
                              </Box>
                            </Box>
                          </Tooltip>
                        </Grid>
                        );
                      })}
                    </Grid>
                    <Divider sx={{ my: 1.5 }} />
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3}>
                      <Typography variant="caption" color="text.secondary">
                        Last AI action:{' '}
                        <strong>{fmtTs(aiStatus.last_ai_action)}</strong>
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Last successful AI response:{' '}
                        <strong>{fmtTs(aiStatus.last_successful_response)}</strong>
                      </Typography>
                    </Stack>
                </CollapsibleCard>
              )}

              {/* Metrics */}
              <Grid container spacing={1.5} sx={{ mb: 2 }}>
                {[
                  { key: 'today', label: 'AI Actions Today' },
                  { key: 'week', label: 'This Week' },
                  { key: 'month', label: 'This Month' },
                  { key: 'total', label: 'Total AI Actions' },
                ].map(({ key, label }) => (
                  <Grid item xs={6} sm={3} key={key}>
                    <Card variant="outlined">
                      <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
                        <Typography variant="h5" fontWeight={700}>{(aiActivity.metrics?.[key] ?? 0).toLocaleString()}</Typography>
                        <Typography variant="caption" color="text.secondary">{label}</Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>

              {/* Category filter */}
              <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: 'wrap', gap: 1 }}>
                {['', 'moderation', 'knowledge', 'engagement', 'automation', 'analytics'].map((c) => (
                  <Chip
                    key={c || 'all'}
                    label={c
                      ? `${c.charAt(0).toUpperCase()}${c.slice(1)} (${aiActivity.by_category?.[c] ?? 0})`
                      : 'All'}
                    size="small"
                    color={aiActivityCategory === c ? 'primary' : 'default'}
                    variant={aiActivityCategory === c ? 'filled' : 'outlined'}
                    onClick={() => setAiActivityCategory(c)}
                    sx={{ textTransform: 'capitalize' }}
                  />
                ))}
              </Stack>

              {/* Timeline */}
              <Card>
                <CardContent>
                  {(!aiActivity.events || aiActivity.events.length === 0) ? (
                    <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: 'center' }}>
                      No AI activity recorded yet. As the bot moderates, answers questions, and runs automations,
                      those actions will appear here.
                    </Typography>
                  ) : (
                    <TableContainer sx={{ overflowX: 'auto', mx: -1, px: 1 }}>
                      <Table size="small" sx={{ minWidth: 520 }}>
                        <TableBody>
                          {aiActivity.events.map((e) => (
                            <AIActivityRow
                              key={e.id} e={e} botId={botId} groupId={groupId}
                              fmtTs={fmtTs} onDone={fetchAIActivity}
                            />
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  )}
                </CardContent>
              </Card>
            </>
          )
        )}

      </Box>

      {/* ── Add Auto-Response Dialog ── */}
      <Dialog open={arDialogOpen} onClose={() => setArDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add Auto-Response Trigger</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 2 }}>
          <TextField label="Trigger Text" fullWidth value={arForm.trigger_text}
            onChange={(e) => setArForm({ ...arForm, trigger_text: e.target.value })}
            helperText="The keyword or phrase that triggers the response" />
          <TextField label="Response Text" fullWidth multiline rows={3} value={arForm.response_text}
            onChange={(e) => setArForm({ ...arForm, response_text: e.target.value })} />
          <FormControl fullWidth>
            <InputLabel>Match Type</InputLabel>
            <Select value={arForm.match_type} label="Match Type"
              onChange={(e) => setArForm({ ...arForm, match_type: e.target.value })}>
              <MenuItem value="contains">Contains</MenuItem>
              <MenuItem value="exact">Exact Match</MenuItem>
              <MenuItem value="starts_with">Starts With</MenuItem>
            </Select>
          </FormControl>
          <FormControlLabel
            control={<Switch checked={arForm.is_case_sensitive}
              onChange={(e) => setArForm({ ...arForm, is_case_sensitive: e.target.checked })} />}
            label="Case sensitive"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setArDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreateAutoResponse} disabled={arSaving}>
            {arSaving ? <CircularProgress size={20} /> : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      <RaidCreator open={raidOpen} onClose={() => setRaidOpen(false)} botId={botId} groupId={groupId} />
    </Box>
  );
}
