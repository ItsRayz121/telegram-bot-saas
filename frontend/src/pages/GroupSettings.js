import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, AppBar, Toolbar, Typography, IconButton, Tabs, Tab,
  Card, CardContent, Button, TextField, Switch, FormControlLabel,
  Grid, CircularProgress, Chip, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, Select, MenuItem,
  FormControl, InputLabel, Pagination, Divider, Dialog, DialogTitle,
  DialogContent, DialogActions, Tooltip, Alert, Stack,
  Menu, ListItemIcon, ListItemText,
  useTheme, useMediaQuery,
} from '@mui/material';
import {
  ArrowBack, Save, Add, Delete, CheckCircle, Schedule,
  Send, Assessment, People, SmartToy,
  Warning as WarningIcon, FileDownload,
  Block, Gavel, VolumeOff, VolumeUp, LockOpen, PersonRemove,
} from '@mui/icons-material';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import useScrollRestore from '../hooks/useScrollRestore';
import TeamAccessDashboard from '../components/TeamAccessDashboard';
import SlowModeGuide from '../components/SlowModeGuide';
import JoinGroupCodeDialog from '../components/JoinGroupCodeDialog';
import { MessagePreview, PreviewPanel } from '../components/preview/MessagePreview';
import { WELCOME_VARS, WELCOME_DM_VARS } from '../components/preview/previewText';
import { VerificationPreview, ModerationNoticePreview } from '../components/preview/FeaturePreviews';
import { toast } from 'react-toastify';
import { settings, digest as digestApi } from '../services/api';
import MembersOverview from '../components/analytics/MembersOverview';
import MembersTable from '../components/analytics/MembersTable';
import LeaderboardPanel from '../components/analytics/LeaderboardPanel';
import AuditLogPanel from '../components/analytics/AuditLogPanel';
import WarningsPanel from '../components/analytics/WarningsPanel';
import DigestPreview from '../components/analytics/DigestPreview';
import AIActivityPanel from '../components/analytics/AIActivityPanel';
import { downloadCsv, exportFilename, fetchAllPages, asText } from '../utils/csvExport';
import { track } from '../services/analytics';
import RaidCreator from '../components/RaidCreator';
import ScheduledMessages from '../components/ScheduledMessages';
import KnowledgeBase from '../components/KnowledgeBase';
import PollCreator from '../components/PollCreator';
import WebhookManager from '../components/WebhookManager';
import WorkspaceForwarding from './WorkspaceForwarding';
import WorkspaceAutomations from './WorkspaceAutomations';
import InviteLinks from '../components/InviteLinks';
import AdminMultiSelect from '../components/AdminMultiSelect';
import CampaignsEntry from '../components/CampaignsEntry';
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
import SettingsTransfer from '../components/SettingsTransfer';
import { TELEGRAM_PACKS } from '../data/blockedWordPacks';

function ProBadge() {
  return <Chip label="Pro" color="primary" size="small" sx={{ ml: 1, height: 18, fontSize: '0.65rem', fontWeight: 700 }} />;
}

function EntBadge() {
  return <Chip label="Enterprise" color="secondary" size="small" sx={{ ml: 1, height: 18, fontSize: '0.65rem', fontWeight: 700 }} />;
}

function DefaultTimezoneCard({ value, onChange }) {
  return (
    <CollapsibleCard id="tg.automation.default_timezone" title="Group Default Timezone" sx={{ mb: 2 }}>
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
    </CollapsibleCard>
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

  // The selected tab, sub-tab and list filters live in the URL (?tab=analytics&sub=Members&page=2)
  // so Back/Forward, refresh and shared links all land on the same screen.
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab');
  const cat = CATEGORIES.some((c) => c.id === tabParam) ? tabParam : 'moderation';
  const subTab = Math.max(0, (CATEGORIES.find((c) => c.id === cat)?.subTabs || []).indexOf(searchParams.get('sub')));
  const goTab = useCallback((catId, subIdx = 0, { replace = false } = {}) => {
    const c = buildCategories(isOfficial).find((x) => x.id === catId);
    if (!c) return;
    const next = new URLSearchParams();
    next.set('tab', catId);
    if (subIdx > 0 && c.subTabs[subIdx]) next.set('sub', c.subTabs[subIdx]);
    setSearchParams(next, { replace });
  }, [isOfficial, setSearchParams]);
  const setSubTab = (i) => goTab(cat, i);
  // Retired "Raids" sub-tab: raids are created as campaigns now. Old links
  // (?tab=community&sub=Raids) land on the campaign list filtered to raids.
  useEffect(() => {
    if (tabParam === 'community' && searchParams.get('sub') === 'Raids') {
      const base = isOfficial ? `/groups/${groupId}/campaigns/all` : `/bot/${botId}/group/${groupId}/campaigns/all`;
      navigate(`${base}?type=raid`, { replace: true });
    }
  }, [tabParam, searchParams, isOfficial, botId, groupId, navigate]);
  const [groupData, setGroupData] = useState(null);
  const [accessRole, setAccessRole] = useState(null); // owner | manager | viewer (null until loaded)
  const [settingsData, setSettingsData] = useState(null);
  const [trustedBotInput, setTrustedBotInput] = useState('');
  const [allowlistInput, setAllowlistInput] = useState('');
  // Snapshot of last-saved settings (JSON string) — used to enable Save only when dirty (#12)
  const [origSettings, setOrigSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [joinCodeOpen, setJoinCodeOpen] = useState(false);
  useScrollRestore(!loading && !!settingsData);

  const [members, setMembers] = useState([]);
  const [membersTotal, setMembersTotal] = useState(0);
  const [membersLoading, setMembersLoading] = useState(false);
  const [membersWarnedOnly, setMembersWarnedOnly] = useState(false);
  // Bumped after any moderation change so the server-side summaries refetch.
  const [insightsKey, setInsightsKey] = useState(0);
  const bumpInsights = useCallback(() => setInsightsKey((k) => k + 1), []);
  const [exporting, setExporting] = useState('');
  const [membersPage, setMembersPage] = useState(() => Math.max(1, Number(searchParams.get('page')) || 1));
  const [membersPages, setMembersPages] = useState(1);
  const [membersSearch, setMembersSearch] = useState(() => (cat === 'analytics' && subTab === 0 ? searchParams.get('q') || '' : ''));
  const [membersSort, setMembersSort] = useState(() => searchParams.get('sort') || 'xp');
  const [membersTimeRange, setMembersTimeRange] = useState(() => searchParams.get('range') || 'all');

  const [leaderboard, setLeaderboard] = useState([]);
  const [leaderboardLoading, setLeaderboardLoading] = useState(false);
  const [leaderboardTimeRange, setLeaderboardTimeRange] = useState(() => searchParams.get('range') || 'all');
  const [leaderboardWalletOnly, setLeaderboardWalletOnly] = useState(false);
  const [leaderboardSearch, setLeaderboardSearch] = useState('');
  const [leaderboardSearchInput, setLeaderboardSearchInput] = useState(() => searchParams.get('q') || '');
  const [leaderboardTotal, setLeaderboardTotal] = useState(0);
  const LEADERBOARD_LIMIT = 100;

  // List filters <-> URL. State is written to the URL with replace (a filter tweak is not a
  // history step); a URL change from Back/Forward is copied back into state.
  const onMembersTab = cat === 'analytics' && subTab === 0;
  const onBoardTab = cat === 'analytics' && subTab === getSubTabIndex(CATEGORIES, 'analytics', 'Leaderboard');
  useEffect(() => {
    const want = new URLSearchParams(searchParams);
    ['page', 'q', 'sort', 'range'].forEach((k) => want.delete(k));
    if (onMembersTab) {
      if (membersPage > 1) want.set('page', String(membersPage));
      if (membersSearch) want.set('q', membersSearch);
      if (membersSort !== 'xp') want.set('sort', membersSort);
      if (membersTimeRange !== 'all') want.set('range', membersTimeRange);
    } else if (onBoardTab) {
      if (leaderboardSearchInput) want.set('q', leaderboardSearchInput);
      if (leaderboardTimeRange !== 'all') want.set('range', leaderboardTimeRange);
    }
    if (want.toString() !== searchParams.toString()) setSearchParams(want, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [membersPage, membersSearch, membersSort, membersTimeRange, leaderboardSearchInput, leaderboardTimeRange]);
  useEffect(() => {
    if (onMembersTab) {
      setMembersPage(Math.max(1, Number(searchParams.get('page')) || 1));
      setMembersSearch(searchParams.get('q') || '');
      setMembersSort(searchParams.get('sort') || 'xp');
      setMembersTimeRange(searchParams.get('range') || 'all');
    } else if (onBoardTab) {
      setLeaderboardSearchInput(searchParams.get('q') || '');
      setLeaderboardTimeRange(searchParams.get('range') || 'all');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const [auditLogs, setAuditLogs] = useState([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditPage, setAuditPage] = useState(1);
  const [auditSearch, setAuditSearch] = useState('');
  const [auditMode, setAuditMode] = useState('grouped');   // grouped | events
  const [auditPeriod, setAuditPeriod] = useState('30d');   // 7d | 30d | 90d | all
  const [auditAction, setAuditAction] = useState('');
  const [expandedLogId, setExpandedLogId] = useState(null);
  const [expandedWarnId, setExpandedWarnId] = useState(null);

  const [autoResponses, setAutoResponses] = useState([]);
  const [arDialogOpen, setArDialogOpen] = useState(false);
  const [arForm, setArForm] = useState({ trigger_text: '', response_text: '', match_type: 'contains', is_case_sensitive: false });
  const [arSaving, setArSaving] = useState(false);

  const [reports, setReports] = useState([]);
  const [reportsLoading, setReportsLoading] = useState(false);

  // Warnings — official groups only
  const [warnings, setWarnings] = useState([]);
  const [warningsLoading, setWarningsLoading] = useState(false);
  const [warningsSearch, setWarningsSearch] = useState('');
  const [warningsTotal, setWarningsTotal] = useState(0);
  const [warningsActiveTotal, setWarningsActiveTotal] = useState(0);
  const [warningsPage, setWarningsPage] = useState(1);
  const [warningsMode, setWarningsMode] = useState('members');   // members | records
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

  // AI Activity tab (the feed + overview live in AIActivityPanel; this is the status card)
  const [aiStatus, setAiStatus] = useState(null);

  // Admin list for reports / digest recipient selection
  const [groupAdmins, setGroupAdmins] = useState([]);
  const [adminsLoading, setAdminsLoading] = useState(false);

  // Command routing / topic access control
  const [cmdRouting, setCmdRouting] = useState({ topics: [], commands: {}, restricted_reply: 'silent', restricted_message: '⚠️ This command is only available in the {topic} topic.' });
  const [routingSaving, setRoutingSaving] = useState(false);

  const [ownTier] = useState(() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}').subscription_tier || 'free'; }
    catch { return 'free'; }
  });
  // On a group shared with you, paid features follow the group OWNER's plan, not yours.
  const [ownerTier, setOwnerTier] = useState(null);
  const userTier = (accessRole && accessRole !== 'owner' && ownerTier) ? ownerTier : ownTier;

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
      setAccessRole(res.data.access_role || null);
      setOwnerTier(res.data.owner_plan || null);
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

  const memberQuery = useCallback(() => {
    const params = { sort_by: membersSort, sort_dir: 'desc' };
    if (membersSearch) params.q = membersSearch;
    if (membersTimeRange && membersTimeRange !== 'all') params.period = membersTimeRange;
    if (membersWarnedOnly) params.has_active_warnings = 'true';
    return params;
  }, [membersSearch, membersTimeRange, membersSort, membersWarnedOnly]);

  const fetchMembers = useCallback(async (page = 1) => {
    setMembersLoading(true);
    try {
      const res = await settings.getMembers(botId, groupId, { ...memberQuery(), page, per_page: 20 });
      setMembers(res.data.members);
      setMembersTotal(res.data.total || 0);
      setMembersPages(res.data.pages || 1);
    } catch {
      toast.error('Failed to load members');
    } finally {
      setMembersLoading(false);
    }
  }, [botId, groupId, memberQuery]);

  // Exports EVERY member matching the current period / search / filters (not just the
  // 20 on screen), walking the paginated endpoint 100 at a time.
  const exportMembersCSV = useCallback(async () => {
    if (exporting) return;
    setExporting('members');
    try {
      const { rows, truncated } = await fetchAllPages(async (page) => {
        const res = await settings.getMembers(botId, groupId, { ...memberQuery(), page, per_page: 100 });
        return { rows: res.data.members || [], pages: res.data.pages || 1 };
      });
      if (!rows.length) { toast.info('Nothing to export for these filters'); return; }
      const xpField = { '1d': 'xp_1d', '7d': 'xp_7d', '30d': 'xp_30d' }[membersTimeRange] || 'xp';
      const xpLabel = { '1d': 'XP (today)', '7d': 'XP (7d)', '30d': 'XP (30d)' }[membersTimeRange] || 'XP (lifetime)';
      downloadCsv(
        exportFilename(groupDisplayName || groupId, 'members', membersTimeRange),
        ['Name', 'Username', 'Telegram ID', xpLabel, 'Level', 'Active warnings', 'Role', 'Verified', 'Muted', 'Wallet submitted', 'Wallet address', 'Joined (UTC)'],
        rows.map((m) => [
          m.first_name || '', m.username ? `@${m.username}` : '', asText(m.telegram_user_id || ''),
          m[xpField] ?? 0, m.level ?? 0, m.active_warnings ?? m.warnings ?? 0, m.role || '',
          !!m.is_verified, !!m.is_muted, !!m.wallet_address, m.wallet_address || '', m.joined_at || '',
        ]),
      );
      toast.success(`Exported ${rows.length.toLocaleString()} member${rows.length === 1 ? '' : 's'}${membersWarnedOnly || membersSearch ? ' (filtered)' : ''}${truncated ? ' - capped at 20,000' : ''}`);
    } catch {
      toast.error('Export failed - nothing was downloaded');
    } finally {
      setExporting('');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [botId, groupId, memberQuery, membersTimeRange, membersWarnedOnly, membersSearch, exporting]);

  const exportLeaderboardCSV = useCallback(() => {
    if (!leaderboard.length) return;
    const xpField = { '1d': 'xp_1d', '7d': 'xp_7d', '30d': 'xp_30d' }[leaderboardTimeRange] || 'xp';
    const xpLabel = { '1d': 'XP (today)', '7d': 'XP (7d)', '30d': 'XP (30d)' }[leaderboardTimeRange] || 'XP (lifetime)';
    downloadCsv(
      exportFilename(groupDisplayName || groupId, 'leaderboard', leaderboardTimeRange),
      ['Rank', 'Name', 'Username', 'Telegram ID', xpLabel, 'Level', 'Role', 'Wallet address'],
      leaderboard.map((m, i) => [
        i + 1, m.first_name || '', m.username ? `@${m.username}` : '', asText(m.telegram_user_id || ''),
        m[xpField] ?? 0, m.level ?? 0, m.role || '', m.wallet_address || '',
      ]),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leaderboard, groupId, leaderboardTimeRange]);

  const fetchLeaderboard = useCallback(async () => {
    setLeaderboardLoading(true);
    try {
      const params = { limit: LEADERBOARD_LIMIT };
      if (leaderboardTimeRange && leaderboardTimeRange !== 'all') params.period = leaderboardTimeRange;
      if (leaderboardWalletOnly) params.has_wallet = 'true';
      if (leaderboardSearch.trim()) params.q = leaderboardSearch.trim();
      const res = await settings.getLeaderboard(botId, groupId, params);
      setLeaderboard(res.data.members || []);
      setLeaderboardTotal(res.data.total_ranked ?? (res.data.members || []).length);
    } catch {
      toast.error('Failed to load leaderboard');
    } finally {
      setLeaderboardLoading(false);
    }
  }, [botId, groupId, leaderboardTimeRange, leaderboardWalletOnly, leaderboardSearch]);

  // Debounce the leaderboard search so typing doesn't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => setLeaderboardSearch(leaderboardSearchInput), 300);
    return () => clearTimeout(t);
  }, [leaderboardSearchInput]);

  const fetchAuditLogs = useCallback(async (page = 1) => {
    try {
      const params = { page, per_page: 20 };
      if (auditSearch.trim()) params.q = auditSearch.trim();
      if (auditPeriod !== 'all') params.days = auditPeriod;
      if (auditAction) params.action_type = auditAction;
      const res = await settings.getAuditLogs(botId, groupId, params);
      setAuditLogs(res.data.logs);
      setAuditTotal(res.data.pages);
    } catch {
      toast.error('Failed to load audit logs');
    }
  }, [botId, groupId, auditSearch, auditPeriod, auditAction]);

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
    if (!(cat === 'analytics' && subTab === warningsSubTabIdx && warningsMode === 'records')) return undefined;
    const t = setTimeout(() => { fetchWarnings({ page: 1, search: warningsSearch }); }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [warningsSearch]);

  const handleRemoveWarning = async (warningId) => {
    try {
      await settings.removeWarning(botId, groupId, warningId);
      toast.success('Warning removed');
      setWarnings(prev => prev.filter(w => w.id !== warningId));
      setWarningsActiveTotal((n) => Math.max(0, n - 1));
      bumpInsights();
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
    try {
      const st = await settings.getAIStatus(botId, groupId);
      setAiStatus(st.data || null);
    } catch {
      setAiStatus(null);
    }
  }, [botId, groupId]);

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
      bumpInsights();
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
  const importExportSubTabIdx = getSubTabIndex(CATEGORIES, 'settings', 'Import & Export');
  const teamAccessSubTabIdx = getSubTabIndex(CATEGORIES, 'settings', 'Team Access');
  // Telegram chat id of this group — forwarding/workflows key on it.
  const groupChatId = groupData?.telegram_group_id || groupId;
  const isViewer = accessRole === 'viewer';
  const backPath = (isOfficial || (accessRole && accessRole !== 'owner')) ? '/groups' : `/bot/${botId}`;
  const groupDisplayName = groupData?.title || groupData?.group_name || groupData?.name || null;
  useEffect(() => { fetchSettings(); }, [fetchSettings]);
  useEffect(() => { if (cat === 'analytics' && subTab === 0) fetchMembers(membersPage); }, [cat, subTab, membersPage, fetchMembers]);
  useEffect(() => { if (cat === 'analytics' && subTab === leaderboardSubTabIdx) fetchLeaderboard(); }, [cat, subTab, leaderboardSubTabIdx, fetchLeaderboard]);
  useEffect(() => { if (cat === 'analytics' && subTab === auditLogSubTabIdx && auditMode === 'events') fetchAuditLogs(auditPage); }, [cat, subTab, auditLogSubTabIdx, auditPage, fetchAuditLogs, auditMode]);
  useEffect(() => { if (cat === 'automation' && subTab === autoReplySubTabIdx) fetchAutoResponses(); }, [cat, subTab, autoReplySubTabIdx, fetchAutoResponses]);
  useEffect(() => { if (cat === 'moderation' && subTab === 2) fetchReports(); }, [cat, subTab, fetchReports]);
  useEffect(() => { if (cat === 'moderation' && subTab === 0) fetchProtectionLog(); }, [cat, subTab, fetchProtectionLog]);
  useEffect(() => { if (cat === 'analytics' && subTab === warningsSubTabIdx && warningsMode === 'records') fetchWarnings(); }, [cat, subTab, warningsSubTabIdx, fetchWarnings, warningsMode]);
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
      if (userTier === 'free' && PRO_GATED_SECTIONS.has(topKey)) {
        setUpgradeFeature(PRO_GATED_LABELS[topKey] || topKey);
        setUpgradeModalOpen(true);
        return;
      }
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

  const handleCatChange = (newCat) => goTab(newCat, 0);

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
    // The API sends UTC timestamps without a zone suffix; without "Z" the browser
    // would read them as local time and shift every time by the viewer's offset.
    const iso = (typeof ts === 'string' && /\d{2}:\d{2}/.test(ts) && !/(Z|[+-]\d\d:?\d\d)$/.test(ts)) ? `${ts}Z` : ts;
    try {
      return new Date(iso).toLocaleString([], { ...opts, timeZone: groupTz });
    } catch {
      return new Date(iso).toLocaleString();
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
    goTab(t.cat, t.sub >= 0 ? t.sub : 0);
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
          <IconButton edge="start" onClick={() => navigate(backPath)} sx={{ mr: 1 }}>
            <ArrowBack />
          </IconButton>
          {/* Breadcrumb nav links — hidden on mobile (back arrow handles the
              "up" action there) to keep the header to a single compact row. */}
          <Box sx={{ display: { xs: 'none', md: 'flex' }, alignItems: 'center', gap: 0.5, mr: 1 }}>
            <Button size="small" variant="text" onClick={() => navigate('/dashboard')} sx={{ fontSize: '0.75rem', px: 1, py: 0.25, minWidth: 0, color: 'text.secondary' }}>
              Dashboard
            </Button>
            <Box component="span" sx={{ color: 'text.disabled', fontSize: '0.75rem' }}>/</Box>
            <Button size="small" variant="text" onClick={() => navigate(backPath)} sx={{ fontSize: '0.75rem', px: 1, py: 0.25, minWidth: 0, color: 'text.secondary' }}>
              {backPath === '/groups' ? 'My Groups' : 'Bot Settings'}
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
            disabled={saving || isViewer || cat === 'analytics' || cat === 'settings' || !isDirty}
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
      {isViewer && (
        <Alert severity="info" sx={{ borderRadius: 0 }}>
          You have <strong>view-only</strong> access to this group. You can look at everything, but changes are turned off.
        </Alert>
      )}

      <Box sx={{
        // Data-heavy tabs (tables) use the full width beside the sidebar; form tabs stay readable at 900.
        maxWidth: (cat === 'analytics' || cat === 'automation') ? 1680 : 900, mx: 'auto', p: { xs: 2, md: 3 },
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
                <PreviewPanel label="Preview notices">
                  <ModerationNoticePreview official={isOfficial} muteMinutes={am.spam?.mute_duration_minutes || 10}
                    autoDelete={mod.auto_delete_warnings !== false} autoDeleteSeconds={mod.auto_delete_warn_seconds ?? 30} />
                </PreviewPanel>
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

            {/* Slow mode: Telegram's native slow mode can't be set by a bot. The old bot-enforced cooldown is
                retired (gated off in the bot by flag bot_slow_mode_enabled); this card is a guide, not a control. */}
            <CollapsibleCard id="tg.moderation.slow_mode" title="🐢 Telegram Slow Mode">
                <SlowModeGuide groupUsername={groupData?.username || groupData?.group_username} hasLegacySetting={!!sm.enabled} />
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
                  Uses your workspace AI key if you added one, otherwise your plan's Platform AI allowance.
                  Only runs when Layers 1 &amp; 2 pass. Skips messages under 10 words. Unsure verdicts never trigger an action.
                </Typography>
                <FormControl size="small" sx={{ minWidth: 220, ml: 4, mb: 1 }} disabled={!(am.smart_mod || {}).ai_enabled}>
                  <InputLabel>AI verdict handling</InputLabel>
                  <Select
                    value={(am.smart_mod || {}).ai_mode || 'enforce'}
                    label="AI verdict handling"
                    onChange={(e) => updateSetting('automod.smart_mod.ai_mode', e.target.value)}
                  >
                    <MenuItem value="enforce">Enforce (apply the action below)</MenuItem>
                    <MenuItem value="observe">Review only (log, take no action)</MenuItem>
                  </Select>
                </FormControl>

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
                  <AdminMultiSelect
                    label="Admins who bypass smart moderation"
                    buttonLabel="Select admins"
                    selectedIds={(am.smart_mod || {}).trusted_users || []}
                    admins={groupAdmins}
                    loading={adminsLoading}
                    onRefresh={fetchAdmins}
                    onChange={(ids) => updateSetting('automod.smart_mod.trusted_users', ids)}
                    helperText="Messages from these admins skip all smart moderation checks. This is separate from who receives report DMs; “Started bot” is not required."
                  />
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
                    <AdminMultiSelect
                      label="Admins to receive report DMs"
                      buttonLabel="Select Admins"
                      selectedIds={rep.selected_admin_ids || []}
                      admins={groupAdmins}
                      loading={adminsLoading}
                      requireDm
                      onChange={(ids) => updateSetting('reports.selected_admin_ids', ids)}
                      helperText="Selected admins receive reports via private DM from @telegizer_bot. They must have started the bot first."
                    />
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
                    <Select value={v.method === 'math' ? 'math' : 'button'} label="Verification Method"
                      onChange={(e) => updateSetting('verification.method', e.target.value)}>
                      <MenuItem value="button">Button Click</MenuItem>
                      <MenuItem value="math">Math Captcha</MenuItem>
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

              <PreviewPanel label="Preview verification message">
                <VerificationPreview official={isOfficial} method={v.method === 'math' ? 'math' : 'button'}
                  timeoutSeconds={v.timeout_seconds ?? 300} maxAttempts={v.max_attempts ?? 3} groupName={groupDisplayName} />
              </PreviewPanel>

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
                {/* Preview only: built from the unsaved form, never sent. Mirrors WelcomeSystem.send_welcome. */}
                {!w.ai_welcome_enabled && (
                  <PreviewPanel label="Preview welcome message">
                    <MessagePreview platform="telegram" kind="welcome message" syntax="python" vars={WELCOME_VARS}
                      text={`${w.message ?? 'Welcome {first_name} to {group_name}! 👋'}${w.show_rules && w.rules_text ? `\n\n📜 *Rules:*\n${String(w.rules_text).replace(/[{}]/g, (c) => c + c)}` : ''}`}
                      buttons={w.rules_text ? [[{ text: '📜 Read Rules' }]] : undefined}
                      media={w.media_url ? { kind: 'Photo', label: String(w.media_url).split('/').pop() } : undefined}
                      destination={`${groupDisplayName || 'Your group'} · when a new member joins${w.delete_after_seconds ? ` · deleted after ${w.delete_after_seconds}s` : ''}`} />
                  </PreviewPanel>
                )}
                {w.ai_welcome_enabled && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                    AI welcome text is written when each member joins, so there is no fixed text to preview.
                  </Typography>
                )}
                {w.ai_welcome_enabled && (
                  <Alert severity="info" sx={{ mt: 2, mb: 2 }}>
                    {settingsData?.workspace_ai_key_set
                      ? 'AI welcome messages are active using the Telegizer platform AI. You can add your own OpenAI key in AI & Integrations if preferred.'
                      : 'AI welcome messages require an OpenAI API key. Add your key in AI & Integrations → Knowledge Base.'}
                  </Alert>
                )}
                {/* mt:1 + the item's 16px padding = 24px clear of the Preview button,
                    so the floating labels never touch it (also at 200% zoom). */}
                <Grid container spacing={2} sx={{ mt: 1 }}>
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
                  {w.dm_enabled && (
                    <PreviewPanel label="Preview DM">
                      <MessagePreview platform="telegram" kind="direct message" syntax="python" vars={WELCOME_DM_VARS}
                        text={w.dm_message || ''} destination="Private chat with the new member" />
                    </PreviewPanel>
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
          <WorkspaceForwarding embeddedGroupId={groupChatId} embeddedGroupName={groupDisplayName} planTier={userTier} />
        )}

        {/* AUTOMATION › Workflows — per-group, source fixed to this group */}
        {cat === 'automation' && subTab === workflowsSubTabIdx && workflowsSubTabIdx >= 0 && (
          <WorkspaceAutomations embeddedGroupId={groupChatId} planTier={userTier} />
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

        {/* COMMUNITY › Invite Links (default sub-tab; Raids retired, raids are campaigns) */}
        {cat === 'community' && subTab === 0 && (
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
        {cat === 'community' && subTab === 1 && (
          <CampaignsEntry botId={botId} groupId={groupId} isOfficial={isOfficial} />
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
        {cat === 'analytics' && subTab === 0 && (
          <>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 1.5 }}>
              <Box>
                <Typography variant="h6" fontWeight={700} component="h2">Members</Typography>
                <Typography variant="caption" color="text.secondary">
                  Summary numbers cover the whole group for the selected period, not just this page.
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                <Button size="small" variant="outlined" startIcon={<People fontSize="small" />}
                  onClick={() => navigate(isOfficial ? `/groups/${groupId}/crm` : `/bot/${botId}/group/${groupId}/crm`)}>
                  Open CRM view
                </Button>
                <Button size="small" variant="outlined"
                  startIcon={exporting === 'members' ? <CircularProgress size={14} /> : <FileDownload fontSize="small" />}
                  onClick={exportMembersCSV} disabled={!membersTotal || !!exporting}>
                  {exporting === 'members' ? 'Exporting…' : `Export ${membersWarnedOnly || membersSearch ? 'filtered' : 'all'} (${membersTotal.toLocaleString()})`}
                </Button>
              </Box>
            </Box>

            <MembersOverview
              botId={botId} groupId={groupId} isOfficial={isOfficial} period={membersTimeRange}
              warnedOnly={membersWarnedOnly} refreshKey={insightsKey}
              onToggleWarned={() => { setMembersWarnedOnly((v) => !v); setMembersPage(1); }}
            />

            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mb: 1.5, alignItems: 'center' }} role="group" aria-label="Member period">
              {[
                { key: 'all', label: 'All time' },
                { key: '30d', label: '30 days' },
                { key: '7d', label: '7 days' },
                { key: '1d', label: 'Today' },
              ].map(({ key, label }) => (
                <Chip
                  key={key} label={label} size="small" clickable aria-pressed={membersTimeRange === key}
                  variant={membersTimeRange === key ? 'filled' : 'outlined'}
                  color={membersTimeRange === key ? 'primary' : 'default'}
                  onClick={() => { setMembersTimeRange(key); setMembersPage(1); }}
                />
              ))}
              <Chip
                label="Active warnings only" size="small" clickable aria-pressed={membersWarnedOnly}
                variant={membersWarnedOnly ? 'filled' : 'outlined'} color={membersWarnedOnly ? 'warning' : 'default'}
                onClick={() => { setMembersWarnedOnly((v) => !v); setMembersPage(1); }}
              />
            </Box>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, mb: 2 }}>
              <TextField
                size="small" placeholder="Search name or @username…" sx={{ flex: '1 1 240px' }}
                inputProps={{ 'aria-label': 'Search members' }}
                value={membersSearch} onChange={(e) => { setMembersSearch(e.target.value); setMembersPage(1); }}
              />
              <FormControl size="small" sx={{ minWidth: 150 }}>
                <InputLabel id="members-sort-label">Sort by</InputLabel>
                <Select labelId="members-sort-label" value={membersSort} label="Sort by" onChange={(e) => { setMembersSort(e.target.value); setMembersPage(1); }}>
                  <MenuItem value="xp">XP</MenuItem>
                  <MenuItem value="level">Level</MenuItem>
                  <MenuItem value="first_name">Name</MenuItem>
                  <MenuItem value="joined_at">Joined</MenuItem>
                  <MenuItem value="warnings">Warnings</MenuItem>
                  <MenuItem value="wallet_address">Wallet</MenuItem>
                </Select>
              </FormControl>
            </Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }} aria-live="polite">
              {membersTotal.toLocaleString()} member{membersTotal === 1 ? '' : 's'} match{membersTotal === 1 ? 'es' : ''}
              {membersWarnedOnly ? ' · holding active warnings' : ''}{membersSearch ? ` · “${membersSearch}”` : ''}
            </Typography>
            <MembersTable
              members={members} loading={membersLoading} period={membersTimeRange} isOfficial={isOfficial}
              botId={botId} groupId={groupId} isMobile={isMobile} fmt={fmtTs}
            />
            {membersPages > 1 && (
              <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
                <Pagination count={membersPages} page={membersPage} onChange={(_, p) => setMembersPage(p)} color="primary" />
              </Box>
            )}
          </>
        )}

        {/* ANALYTICS › Leaderboard */}
        {cat === 'analytics' && subTab === leaderboardSubTabIdx && (
          <LeaderboardPanel
            members={leaderboard} loading={leaderboardLoading} period={leaderboardTimeRange} onPeriod={setLeaderboardTimeRange}
            walletOnly={leaderboardWalletOnly} onWalletOnly={setLeaderboardWalletOnly}
            search={leaderboardSearchInput} onSearch={setLeaderboardSearchInput}
            totalRanked={leaderboardTotal} limit={LEADERBOARD_LIMIT} onExport={exportLeaderboardCSV}
            isOfficial={isOfficial} botId={botId} groupId={groupId} isMobile={isMobile}
          />
        )}

        {/* ANALYTICS › Audit Log / Mod Log */}
        {cat === 'analytics' && subTab === auditLogSubTabIdx && (
          <AuditLogPanel
            botId={botId} groupId={groupId} isOfficial={isOfficial} fmt={fmtTs} refreshKey={insightsKey}
            mode={auditMode} onMode={setAuditMode}
            period={auditPeriod} onPeriod={(p) => { setAuditPeriod(p); setAuditPage(1); }}
            search={auditSearch} onSearch={(v) => { setAuditSearch(v); setAuditPage(1); }}
            actionType={auditAction} onActionType={(v) => { setAuditAction(v); setAuditPage(1); }}
            renderActions={(uid, uname) => (
              <ModerationActions botId={botId} groupId={groupId} userId={uid} username={uname}
                onDone={() => { bumpInsights(); fetchAuditLogs(auditPage); }} />
            )}
          >
          <>
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
                            onDone={() => { bumpInsights(); fetchAuditLogs(auditPage); fetchWarnings({ page: 1 }); }}
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
                              onDone={() => { bumpInsights(); fetchAuditLogs(auditPage); fetchWarnings({ page: 1 }); }}
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
          </AuditLogPanel>
        )}

        {/* ANALYTICS › Warnings */}
        {cat === 'analytics' && subTab === warningsSubTabIdx && (() => {
          // Search + pagination are server-side now, so the loaded rows ARE the
          // result set (no client-side cap that made the count stick at 200).
          const filteredWarnings = warnings;
          return (
          <WarningsPanel
            botId={botId} groupId={groupId} isOfficial={isOfficial} fmt={fmtTs} isViewer={isViewer}
            mode={warningsMode} onMode={setWarningsMode} refreshKey={insightsKey} onChanged={bumpInsights}
            renderActions={(uid, uname) => (
              <ModerationActions botId={botId} groupId={groupId} userId={uid} username={uname} onDone={bumpInsights} />
            )}
          >
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
                              onDone={() => { bumpInsights(); fetchWarnings({ page: 1 }); }}
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
                                    onDone={() => { bumpInsights(); fetchWarnings({ page: 1 }); }}
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
          </WarningsPanel>
          );
        })()}


        {/* ANALYTICS › Digest */}
        {cat === 'analytics' && subTab === digestSubTabIdx && (
          digestLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}><CircularProgress /></Box>
          ) : (
            <>
              <DigestPreview
                botId={botId} groupId={groupId} config={digestConfig} fmt={fmtTs} refreshKey={insightsKey}
                botLabel={isOfficial ? 'Telegizer' : (groupData?.bot_username ? `@${groupData.bot_username}` : 'Your bot')}
              />
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
          (
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

              <AIActivityPanel botId={botId} groupId={groupId} fmt={fmtTs} refreshKey={insightsKey} />
            </>
          )
        )}

        {/* ── Settings › Team Access (group-scoped; whole-bot sharing stays on My Groups) ── */}
        {cat === 'settings' && subTab === teamAccessSubTabIdx && teamAccessSubTabIdx >= 0 && (
          accessRole === 'owner' ? (
            <Box>
              <TeamAccessDashboard group={{ telegram_group_id: groupChatId, title: groupDisplayName }}
                onJoinCode={() => setJoinCodeOpen(true)} />
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 2 }}>
                This is access to this group only. To give someone every group a bot manages, use
                "Share a whole bot" on My Groups; that is a broader permission.
              </Typography>
            </Box>
          ) : (
            <Card sx={{ maxWidth: 760 }}>
              <CardContent>
                <Typography variant="h6" fontWeight={700} component="h2" sx={{ mb: 0.5 }}>Team access</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ my: 1 }}>
                  Only the group owner can invite or remove people. You have {accessRole || 'limited'} access to this group.
                </Typography>
                <Button size="small" variant="outlined" sx={{ mt: 2 }} onClick={() => setJoinCodeOpen(true)}>
                  Join with access code
                </Button>
              </CardContent>
            </Card>
          )
        )}
        <JoinGroupCodeDialog open={joinCodeOpen} onClose={() => setJoinCodeOpen(false)}
          onJoined={() => { setJoinCodeOpen(false); toast.success('Access granted'); navigate('/groups'); }} />

        {/* ── Settings › Import & Export ── */}
        {cat === 'settings' && subTab === importExportSubTabIdx && importExportSubTabIdx >= 0 && (
          <SettingsTransfer
            scopeLabel="group"
            fileStem={`telegizer-${(groupData?.group_name || 'group').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'group'}`}
            isPaid={userTier !== 'free'}
            onExport={() => settings.exportGroupSettings(botId, groupId)}
            onImport={(file, dryRun) => settings.importGroupSettings(botId, groupId, file, dryRun)}
            onImported={(next) => {
              if (next) {
                setSettingsData(next);
                setOrigSettings(JSON.stringify(next || {}));
              } else {
                fetchSettings();
              }
            }}
          />
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
          {arForm.response_text && (
            <PreviewPanel>
              {/* Auto-replies go out as a plain-text reply to the matching message (no parse mode). */}
              <MessagePreview platform="telegram" syntax="none" plain kind="auto-reply" text={arForm.response_text}
                replyTo={{ author: 'A member', text: arForm.match_type === 'exact' ? arForm.trigger_text || '…' : arForm.match_type === 'starts_with' ? `${arForm.trigger_text || '…'} …` : `… ${arForm.trigger_text || '…'} …` }}
                destination="Reply posted in the group when a message matches" />
            </PreviewPanel>
          )}
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
