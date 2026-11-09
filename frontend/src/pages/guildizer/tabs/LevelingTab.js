import React, { useCallback, useEffect, useState, useMemo } from 'react';
import {
  Box, Grid, Typography, Switch, FormControlLabel, TextField,
  MenuItem, Button, List, ListItem, ListItemText, Chip, CircularProgress, Alert,
  Snackbar, Stack, IconButton,
} from '@mui/material';
import { Add, Delete } from '@mui/icons-material';
import { MessagePreview, PreviewPanel } from '../../../components/preview/MessagePreview';
import { toast } from 'react-toastify';
import guildizerApi from '../../../services/guildizerApi';
import GuildizerCollapsibleCard from '../../../components/guildizer/GuildizerCollapsibleCard';
import { useSaveBar } from './saveBar';
import { CreateRoleDialog } from './RoleHub';
import CommandManagementTable, { useCommandTable } from '../../../components/CommandManagementTable';

const TEXT_TYPES = new Set([0, 5]);
const PENALTY_ROWS = [['warn', 'Warn'], ['timeout', 'Temporary mute (Timeout)'], ['kick', 'Kick'], ['ban', 'Ban']];
const PENALTY_MODES = [['none', 'No deduction'], ['fixed', 'Fixed XP'], ['percent', 'Percentage of current XP'], ['reset', 'Reset XP to zero']];
// Mirrors backend leveling.compute_penalty (display only; the server computes the real debit).
const penaltyPreview = (xp, mode, v) => {
  if (mode === 'reset') return xp;
  if (mode === 'percent') return Math.min(xp, Math.floor((xp * Math.min(100, v) + 50) / 100));
  return Math.min(xp, v);
};
const VOICE_TYPE = 2;

export default function LevelingTab({ guildId, channels = [], roles = [] }) {
  const [cfg, setCfg] = useState(null);
  const [orig, setOrig] = useState(null);
  const [board, setBoard] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);
  const [sampleXp, setSampleXp] = useState(200);
  const [createFor, setCreateFor] = useState(null);     // milestone index awaiting a new role
  const [extraRoles, setExtraRoles] = useState([]);       // roles created here, before the page re-syncs
  const [safeIds, setSafeIds] = useState(null);          // role ids the server says are safe to auto-assign

  const loadCmdTable = useCallback(() => guildizerApi.get(`/api/guilds/${guildId}/command-table`), [guildId]);
  const saveCmdTable = useCallback((commands) => guildizerApi.put(`/api/guilds/${guildId}/command-table`, { commands }), [guildId]);
  const cmdTable = useCommandTable({
    load: loadCmdTable,
    save: saveCmdTable,
    onSaved: () => toast.success('Command settings saved!'),
    onError: (e) => toast.error(e?.response?.data?.error || 'Could not save the command settings'),
  });

  const textChannels = channels.filter((c) => TEXT_TYPES.has(c.type));
  const voiceChannels = channels.filter((c) => c.type === VOICE_TYPE);
  const assignableRoles = roles.filter((r) => !r.managed && r.name !== '@everyone');
  const allRoles = [...assignableRoles, ...extraRoles.filter((x) => !assignableRoles.some((r) => r.id === x.id))];
  const rewardRoles = safeIds ? allRoles.filter((r) => safeIds.has(r.id) || extraRoles.some((x) => x.id === r.id)) : allRoles;
  const roleName = (id) => allRoles.find((r) => r.id === id)?.name || id;

  useEffect(() => {
    // Which roles are safe to hand out automatically (no moderation/management permissions).
    guildizerApi.get(`/api/guilds/${guildId}/roles/overview`)
      .then(({ data }) => setSafeIds(new Set(data.roles.filter((r) => r.assignable).map((r) => r.id))))
      .catch(() => setSafeIds(null));
  }, [guildId]);

  useEffect(() => {
    Promise.all([
      guildizerApi.get(`/api/guilds/${guildId}/leveling`),
      guildizerApi.get(`/api/guilds/${guildId}/leaderboard?limit=10`).catch(() => ({ data: { leaderboard: [] } })),
    ]).then(([s, b]) => { setCfg(s.data); setOrig(JSON.stringify(s.data)); setBoard(b.data.leaderboard || []); })
      .catch(() => setError('Failed to load leveling.'))
      .finally(() => setLoading(false));
  }, [guildId]);

  const set = (patch) => setCfg((c) => ({ ...c, ...patch }));
  const setL2 = (patch) => setCfg((c) => ({ ...c, leveling2: { ...c.leveling2, ...patch } }));
  const setVoice = (patch) => setCfg((c) => ({ ...c, voice: { ...c.voice, ...patch } }));

  async function save() {
    setSaving(true); setError(null);
    try { const armed = ['warn', 'timeout', 'kick', 'ban'].some((k) => cfg.leveling2?.[`penalty_${k}_mode`] === 'reset');
      const { data } = await guildizerApi.put(`/api/guilds/${guildId}/leveling`, armed ? { ...cfg, confirm_reset: true } : cfg); setCfg(data); setOrig(JSON.stringify(data)); setSaved(true); }
    catch (e) {
      setError(e?.response?.data?.error === 'role_not_assignable'
        ? 'A milestone uses a role with moderation or management permissions. Pick a plain role instead.'
        : 'Save failed.');
    } finally { setSaving(false); }
  }

  const dirty = useMemo(() => cfg != null && orig != null && JSON.stringify(cfg) !== orig, [cfg, orig]);
  const sb = useSaveBar({ save, dirty, saving });

  if (loading) return <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}><CircularProgress /></Box>;
  if (!cfg) return <Alert severity="warning">{error || 'No settings.'}</Alert>;

  const l2 = cfg.leveling2 || {};
  const rewards = l2.role_rewards || [];
  // "next rank in N XP" from the saved milestone ladder (level N needs (N - 1) x 100 XP).
  const nextRank = (m) => {
    const next = [...rewards].filter((r) => r.role_id && Number(r.level) > Number(m.level)).sort((a, b) => a.level - b.level)[0];
    if (!next) return rewards.length ? 'Top rank reached' : undefined;
    return `${Math.max(0, (Number(next.level) - 1) * 100 - Number(m.xp || 0))} XP to ${roleName(next.role_id)} (level ${next.level})`;
  };
  const numL2 = (label, key, max = 1000) => (
    <TextField type="number" size="small" margin="dense" fullWidth label={label}
      value={l2[key] ?? 0} inputProps={{ min: 0, max }} onChange={(e) => setL2({ [key]: Number(e.target.value) })} />
  );

  return (
    <Grid container spacing={2}>
      <Grid item xs={12}>
        <GuildizerCollapsibleCard id="members.leveling.xp_level_system" title="XP & Level System">
          <FormControlLabel control={<Switch checked={cfg.levels_enabled} onChange={(e) => set({ levels_enabled: e.target.checked })} />} label="Award XP for chatting (100 XP per level)" />
          <TextField type="number" size="small" margin="dense" fullWidth label="XP per message"
            value={cfg.xp_per_message} inputProps={{ min: 0, max: 1000 }} onChange={(e) => set({ xp_per_message: Number(e.target.value) })} />
          <TextField type="number" size="small" margin="dense" fullWidth label="Cooldown between awards (seconds)"
            value={cfg.xp_cooldown_seconds} inputProps={{ min: 0, max: 3600 }} onChange={(e) => set({ xp_cooldown_seconds: Number(e.target.value) })} />
          {numL2('XP per reaction received (0 = off)', 'xp_per_reaction')}
          {numL2('Reaction XP cooldown (seconds)', 'reaction_cooldown_seconds', 3600)}
          <FormControlLabel control={<Switch checked={cfg.announce_level_up} onChange={(e) => set({ announce_level_up: e.target.checked })} />} label="Announce level-ups" />
          <FormControlLabel
            control={<Switch checked={!!l2.ai_levelup} onChange={(e) => setL2({ ai_levelup: e.target.checked })} />}
            label={(
              <Stack direction="row" spacing={1} alignItems="center">
                <span>AI-generated level-up line</span>
                <Chip label="Pro" color="primary" size="small" sx={{ height: 18, fontSize: '0.65rem', fontWeight: 700 }} />
              </Stack>
            )}
          />
          <Typography variant="caption" color="text.secondary" display="block" ml={4} mb={0.5} mt={-0.5}>
            Adds a fresh AI congrats sentence under the announce. Needs an AI key on the backend.
          </Typography>
          <TextField select size="small" margin="dense" fullWidth label="Announce in channel"
            value={cfg.levelup_channel_id || ''} onChange={(e) => set({ levelup_channel_id: e.target.value || null })}>
            <MenuItem value="">— same channel as message —</MenuItem>
            {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
          </TextField>
          <TextField size="small" margin="dense" fullWidth label="Level-up message" placeholder="🎉 {user} reached level {level}!"
            value={cfg.levelup_message} inputProps={{ maxLength: 1000 }} onChange={(e) => set({ levelup_message: e.target.value })}
            helperText="Placeholders: {user} {username} {level}" />
          {/* Preview only: mirrors leveling.render_levelup. Nothing is posted. */}
          <PreviewPanel label="Preview level-up message">
            <MessagePreview platform="discord" syntax="single" kind="level-up message" botName="Guildizer"
              vars={{ user: '<@123456789012345678>', username: 'alex', level: '7' }}
              text={cfg.levelup_message || '\u{1F389} {user} reached **level {level}**!'}
              destination={cfg.levelup_channel_id ? 'The chosen announce channel' : 'The channel where the member levelled up'}
              notes={[
                ...(cfg.announce_level_up === false ? ['Level-up announcements are switched off, so this message is not posted.'] : []),
                ...(l2.ai_levelup ? ['A short AI congratulations line is added under this message; it is not part of this preview.'] : []),
                ...(l2.levelup_delete_after_seconds ? [`The message is deleted after ${l2.levelup_delete_after_seconds} seconds.`] : []),
              ]} />
          </PreviewPanel>
          {numL2('Delete level-up message after (seconds, 0 = keep)', 'levelup_delete_after_seconds', 86400)}
          <TextField
            select size="small" margin="dense" fullWidth
            label="Channels where /rank & /leaderboard work"
            value={l2.command_channel_ids || []}
            SelectProps={{
              multiple: true,
              renderValue: (sel) => (sel && sel.length)
                ? `${sel.length} channel${sel.length > 1 ? 's' : ''}`
                : 'All channels',
            }}
            onChange={(e) => setL2({
              command_channel_ids: typeof e.target.value === 'string'
                ? e.target.value.split(',')
                : e.target.value,
            })}
            helperText="Leave empty to allow level commands in every channel.">
            {textChannels.map((c) => <MenuItem key={c.id} value={c.id}># {c.name}</MenuItem>)}
          </TextField>
        </GuildizerCollapsibleCard>
      </Grid>

      <Grid item xs={12}>
        <GuildizerCollapsibleCard id="members.leveling.command_management" title="Command Management">
          <Typography variant="body2" color="text.secondary" mb={2}>
            One row per command. The timer starts when the bot's reply is sent, and the reply is then deleted by the
            server (also after a restart). Private replies are never touched.
          </Typography>
          <CommandManagementTable
            rows={cmdTable.rows}
            limits={cmdTable.limits}
            failures={cmdTable.failures}
            loading={cmdTable.loading}
            saving={cmdTable.saving}
            dirty={cmdTable.dirty}
            invalid={cmdTable.rows.some((r) => r._invalid)}
            accessMode="fixed"
            accessLabel={(row) => ((row.command === '/rank' || row.command === '/leaderboard') && (l2.command_channel_ids || []).length
              ? `${l2.command_channel_ids.length} channel${l2.command_channel_ids.length > 1 ? 's' : ''}`
              : 'Everyone')}
            onChange={cmdTable.change}
            onSave={() => cmdTable.save()}
          />
        </GuildizerCollapsibleCard>
      </Grid>

      <Grid item xs={12}>
        <GuildizerCollapsibleCard id="members.leveling.xp_penalties" title="XP Penalties (Moderation Actions)">
          <Typography variant="caption" color="text.secondary" display="block" mb={1}>
            XP removed per moderation action. XP never drops below 0, earned roles are kept, and one
            action costs one deduction — a warning that escalates to a timeout/kick/ban is charged
            only the escalation&apos;s penalty, not both.
          </Typography>
          {PENALTY_ROWS.map(([kind, label]) => {
            const mode = l2[`penalty_${kind}_mode`] || 'fixed';
            const val = l2[`penalty_${kind}`] ?? 0;
            const eff = mode === 'fixed' && !val ? 'none' : mode;
            return (
              <Stack key={kind} direction="row" spacing={1} alignItems="center" mb={1} flexWrap="wrap" useFlexGap>
                <Typography variant="body2" sx={{ width: 150, flexShrink: 0 }}>{label}</Typography>
                <TextField select size="small" label="Mode" value={eff === 'none' ? 'none' : mode} sx={{ width: 190 }}
                  onChange={(e) => {
                    const m = e.target.value;
                    if (m === 'reset' && !window.confirm(`Reset a member's XP to zero every time they are ${label.toLowerCase()}? This is severe.`)) return;
                    setL2({
                      [`penalty_${kind}_mode`]: m === 'none' ? 'fixed' : m,
                      // a leftover fixed amount (e.g. 500) must not become "100 %" when the mode flips to percent
                      ...(m === 'none' ? { [`penalty_${kind}`]: 0 } : {}),
                      ...(m === 'percent' ? { [`penalty_${kind}`]: val >= 1 && val <= 100 ? val : 10 } : {}),
                    });
                  }}>
                  {PENALTY_MODES.map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}
                </TextField>
                {(eff === 'fixed' || eff === 'percent') && (
                  <TextField type="number" size="small" label={eff === 'percent' ? '% of current XP' : 'XP'} value={val} sx={{ width: 130 }}
                    inputProps={{ min: 0, max: eff === 'percent' ? 100 : 10000 }}
                    onChange={(e) => setL2({ [`penalty_${kind}`]: Math.max(0, Math.min(eff === 'percent' ? 100 : 10000, Number(e.target.value))) })} />
                )}
                <Typography variant="caption" color="text.secondary" sx={{ minWidth: 70 }}>
                  {eff === 'none' ? '—' : `−${penaltyPreview(sampleXp, eff, val)} XP`}
                </Typography>
              </Stack>
            );
          })}
          <TextField type="number" size="small" label="Preview with member XP" value={sampleXp} sx={{ width: 190, mt: 0.5 }}
            inputProps={{ min: 0, max: 1000000 }} onChange={(e) => setSampleXp(Math.max(0, Number(e.target.value)))}
            helperText="Percent uses current XP, rounds half up." />
        </GuildizerCollapsibleCard>
      </Grid>

      {/* Rank Card Style sits before Level → role rewards to match Telegizer's XP card order. */}
      <Grid item xs={12}>
        <GuildizerCollapsibleCard id="members.leveling.rank_card_style" title="🏅 Rank Card Style">
          <Typography variant="caption" color="text.secondary" display="block" mb={1.5}>
            Colours for the image shown by <code>/rank</code> — a gradient background and an accent XP bar.
          </Typography>
          <Grid container spacing={2}>
            {[
              ['Background start', 'bg_color_start', '#1a1a2e'],
              ['Background end', 'bg_color_end', '#16213e'],
              ['Accent', 'accent_color', '#5865F2'],
            ].map(([label, key, fallback]) => (
              <Grid item xs={12} sm={4} key={key}>
                <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>{label}</Typography>
                <input type="color" value={(l2.rank_card || {})[key] || fallback}
                  onChange={(e) => setL2({ rank_card: { ...(l2.rank_card || {}), [key]: e.target.value } })}
                  style={{ width: '100%', height: 40, borderRadius: 8, border: '1px solid #30363d', cursor: 'pointer', background: 'transparent' }} />
              </Grid>
            ))}
          </Grid>
        </GuildizerCollapsibleCard>
      </Grid>

      <Grid item xs={12}>
        <GuildizerCollapsibleCard id="members.leveling.level_role_rewards" title="Level → role milestones">
          <Typography variant="caption" color="text.secondary" display="block" mb={1}>
            Each rank is a real Discord role granted once when a member reaches the level (100 XP per level, so
            level N needs (N − 1) × 100 XP). Guildizer&apos;s role must sit above any role it assigns. Roles with
            moderation or management permissions can&apos;t be used. XP penalties never remove an earned rank.
          </Typography>
          {rewards.map((r, i) => {
            const upd = (patch) => setL2({ role_rewards: rewards.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
            const next = rewards[i + 1];
            return (
              <Stack key={i} direction="row" spacing={1} alignItems="center" mb={1} flexWrap="wrap" useFlexGap>
                <TextField type="number" size="small" label="Level" value={r.level}
                  inputProps={{ min: 1, max: 1000 }} sx={{ width: 90 }}
                  onChange={(e) => upd({ level: Math.max(1, Number(e.target.value)) })} />
                <Chip size="small" variant="outlined" label={`${((Number(r.level) || 1) - 1) * 100} XP`} sx={{ minWidth: 80 }} />
                <TextField select size="small" label="Role" value={r.role_id || ''} sx={{ flex: '1 1 180px', minWidth: 0 }}
                  onChange={(e) => upd({ role_id: e.target.value })}>
                  {rewardRoles.map((ar) => <MenuItem key={ar.id} value={ar.id}>{ar.name}</MenuItem>)}
                  {r.role_id && !rewardRoles.some((ar) => ar.id === r.role_id) && (
                    <MenuItem value={r.role_id}>{roleName(r.role_id)}</MenuItem>
                  )}
                </TextField>
                <Button size="small" onClick={() => setCreateFor(i)}>New role</Button>
                <IconButton aria-label="Delete milestone" size="small" onClick={() => setL2({ role_rewards: rewards.filter((_, j) => j !== i) })}>
                  <Delete fontSize="small" />
                </IconButton>
                {next && next.level <= r.level && (
                  <Typography variant="caption" color="warning.main" sx={{ width: '100%' }}>Levels should increase down the list.</Typography>
                )}
              </Stack>
            );
          })}
          <TextField select size="small" label="When a higher rank is earned" value={l2.role_reward_mode || 'stack'} sx={{ mt: 0.5, mb: 1, minWidth: 260 }}
            onChange={(e) => setL2({ role_reward_mode: e.target.value })}
            helperText={(l2.role_reward_mode || 'stack') === 'replace' ? 'Lower ladder roles are removed (only ones on this ladder).' : 'Keep every rank earned so far.'}>
            <MenuItem value="stack">Keep earlier ranks</MenuItem>
            <MenuItem value="replace">Replace with the new rank</MenuItem>
          </TextField>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button size="small" startIcon={<Add />}
              disabled={rewards.length >= 20 || rewardRoles.length === 0}
              onClick={() => setL2({ role_rewards: [...rewards, { level: (rewards[rewards.length - 1]?.level || 0) + 5, role_id: rewardRoles[0]?.id }] })}>
              Add milestone
            </Button>
            {rewards.length > 0 && (
              <Button size="small" variant="outlined"
                onClick={() => guildizerApi.post(`/api/guilds/${guildId}/leveling/resync-roles`)
                  .then(() => toast.success('Checking every member against the ladder. Missing roles are granted within a few minutes.'))
                  .catch(() => toast.error('Save the ladder first, then try again.'))}>
                Sync roles for existing members
              </Button>
            )}
            {rewards.length === 0 && (
              <Button size="small" variant="outlined" disabled={rewardRoles.length === 0}
                onClick={() => setL2({
                  // Starter tiers. Each row defaults to your first role: pick or create the matching role, then Save.
                  role_rewards: [1, 5, 10, 20, 30, 40, 50, 60, 75, 100]
                    .map((level) => ({ level, role_id: rewardRoles[0]?.id })),
                })}>
                Load 10-level starter template
              </Button>
            )}
          </Stack>
          {rewards.length === 0 && rewardRoles.length === 0 && (
            <Typography variant="caption" color="text.secondary" display="block" mt={1}>
              No safe roles yet — use <b>New role</b> on a milestone, or create roles in your server first.
            </Typography>
          )}
          <CreateRoleDialog guildId={guildId} open={createFor != null} onClose={() => setCreateFor(null)}
            onCreated={(role, existed) => {
              setExtraRoles((er) => [...er.filter((x) => x.id !== role.id), role]);
              if (createFor != null) setL2({ role_rewards: rewards.map((x, j) => (j === createFor ? { ...x, role_id: role.id } : x)) });
              if (existed) setCreateFor(null);
            }} />
        </GuildizerCollapsibleCard>
      </Grid>

      <Grid item xs={12}>
        <GuildizerCollapsibleCard id="members.leveling.voice" title="🎙️ Voice">
          <Typography variant="caption" color="text.secondary" display="block" mb={1}>
            Voice XP is granted every 5 minutes to members actively in voice (AFK channel,
            deafened members and near-empty channels don't count). Needs XP enabled above.
          </Typography>
          <TextField type="number" size="small" margin="dense" fullWidth label="XP per voice minute (0 = off)"
            value={cfg.voice?.xp_per_minute ?? 0} inputProps={{ min: 0, max: 100 }}
            onChange={(e) => setVoice({ xp_per_minute: Number(e.target.value) })} />
          <TextField type="number" size="small" margin="dense" fullWidth label="Minimum people in the channel"
            value={cfg.voice?.min_humans ?? 2} inputProps={{ min: 1, max: 20 }}
            onChange={(e) => setVoice({ min_humans: Number(e.target.value) })} />
          <FormControlLabel control={<Switch checked={!!cfg.voice?.j2c_enabled} onChange={(e) => setVoice({ j2c_enabled: e.target.checked })} />}
            label="Join-to-create voice rooms" />
          <Typography variant="caption" color="text.secondary" display="block" mb={1}>
            Members joining the lobby get their own temporary voice room (deleted when empty).
            Needs Manage Channels + Move Members.
          </Typography>
          <TextField select size="small" margin="dense" fullWidth label="Lobby voice channel"
            value={cfg.voice?.j2c_lobby_channel_id || ''} onChange={(e) => setVoice({ j2c_lobby_channel_id: e.target.value || null })}>
            <MenuItem value="">— pick a voice channel —</MenuItem>
            {voiceChannels.map((c) => <MenuItem key={c.id} value={c.id}>🔊 {c.name}</MenuItem>)}
          </TextField>
          <TextField size="small" margin="dense" fullWidth label="Room name template" placeholder="{user}'s room"
            value={cfg.voice?.j2c_name_template ?? ''} inputProps={{ maxLength: 100 }}
            onChange={(e) => setVoice({ j2c_name_template: e.target.value })}
            helperText="Placeholder: {user}" />
          <TextField type="number" size="small" margin="dense" fullWidth label="Room user limit (0 = unlimited)"
            value={cfg.voice?.j2c_user_limit ?? 0} inputProps={{ min: 0, max: 99 }}
            onChange={(e) => setVoice({ j2c_user_limit: Number(e.target.value) })} />
        </GuildizerCollapsibleCard>
      </Grid>

      <Grid item xs={12}>
        <GuildizerCollapsibleCard id="gz.leveling.leaderboard" title="Leaderboard">
          {board.length === 0 && <Typography variant="body2" color="text.secondary">No XP earned yet.</Typography>}
          <List dense>
            {board.map((m) => (
              <ListItem key={m.user_id} disableGutters secondaryAction={<Typography variant="caption" color="text.secondary">{m.xp} XP</Typography>}>
                <Typography variant="body2" fontWeight={700} color="primary.main" sx={{ width: 34 }}>#{m.rank}</Typography>
                <ListItemText primary={m.username || m.user_id} primaryTypographyProps={{ noWrap: true }}
                  secondary={nextRank(m)} />
                <Chip size="small" label={`Lvl ${m.level}`} sx={{ mr: 1 }} />
              </ListItem>
            ))}
          </List>
        </GuildizerCollapsibleCard>
      </Grid>

      {!sb && (
        <Grid item xs={12} sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2, alignItems: 'center' }}>
          {error && <Alert severity="error" sx={{ py: 0 }}>{error}</Alert>}
          <Button variant="contained" onClick={save} disabled={saving || !dirty}>{saving ? 'Saving…' : dirty ? 'Save changes' : 'Saved'}</Button>
        </Grid>
      )}
      {sb && error && <Grid item xs={12}><Alert severity="error">{error}</Alert></Grid>}

      <Snackbar open={saved} autoHideDuration={2500} onClose={() => setSaved(false)} message="Saved"
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Grid>
  );
}
