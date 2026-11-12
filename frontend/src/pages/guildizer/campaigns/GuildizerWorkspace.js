import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import guildizerApi, { guildizerCampaignWorkspace as wsApi, guildizerEngagement as eng } from '../../../services/guildizerApi';
import {
  CampaignEditDialog, CampaignManageDialog, CampaignWizard, PostStatusCell, ScreenshotViewer, TYPES, XKeyDialog,
} from '../tabs/CampaignsTab';
import { WorkspaceContext, useWorkspace } from '../../campaigns/common';
import { WorkspaceBody } from '../../campaigns/Workspace';

/**
 * Guildizer's campaign workspace. The pages (Overview / Campaigns / Review queue / campaign
 * detail / create) are the SAME components Telegizer uses (pages/campaigns); this file only
 * supplies the Discord side: the server as the boundary, the guildizerApi data calls and the
 * Discord forms. See PARITY_CAMPAIGNS.md for the screen-by-screen matrix.
 */

const TEXT_CHANNEL_TYPES = new Set([0, 5]);

// Servers have no time-zone setting, so times follow the viewer's own browser (labelled on every page).
const browserTz = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; } catch { return 'UTC'; } };

// Discord forms, pre-bound to the current server. Stable component identities (no remounts).
function useDc() {
  const ws = useWorkspace();
  return { guildId: ws.groupId, channels: ws.channels, isPaid: ws.isPaid };
}
function DcWizard(p) { const ws = useWorkspace(); return <CampaignWizard {...useDc()} groupName={ws.groupName} {...p} />; }
function DcManage(p) { return <CampaignManageDialog {...useDc()} {...p} />; }
function DcEdit(p) { return <CampaignEditDialog {...useDc()} {...p} />; }
function DcPostStatus(p) { const { guildId } = useDc(); return <PostStatusCell guildId={guildId} {...p} />; }
function DcScreenshot({ s }) { return <ScreenshotViewer url={s.file_url} />; }
const discordUi = { TYPES, Wizard: DcWizard, Manage: DcManage, Edit: DcEdit, PostStatus: DcPostStatus, Screenshot: DcScreenshot, XKeyDialog };

/** The review guard answers 409 {error:'STALE_SUBMISSION', message}; the shared queue reads {code, error}. */
function normalizeStale(e) {
  const d = e?.response?.data;
  if (e?.response?.status === 409 && d) {
    e.response.data = { ...d, code: 'STALE_SUBMISSION', error: d.message || 'This submission was already reviewed by someone else.' };
  }
  throw e;
}

export function GuildizerWorkspaceProvider({ children }) {
  const { guildId } = useParams();
  const [info, setInfo] = useState({ loading: true, error: null, guild: null });
  const [tick, setTick] = useState(0);
  const [role, setRole] = useState(null);     // owner | manager | viewer (team seat), null until known
  const bump = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    let alive = true;
    setInfo({ loading: true, error: null, guild: null });
    guildizerApi.get(`/api/guilds/${guildId}`)
      .then(({ data }) => { if (alive) setInfo({ loading: false, error: null, guild: data }); })
      .catch((e) => {
        if (!alive) return;
        const st = e?.response?.status;
        setInfo({
          loading: false, guild: null,
          error: st === 403 ? "You can't manage this server." : st === 404 ? 'This server was not found.'
            : st === 401 ? 'Connect your Discord account first.' : 'Could not load this server.',
        });
      });
    return () => { alive = false; };
  }, [guildId]);

  // Read-only team seats ('viewer') must not see edit/review controls (the backend refuses their writes anyway).
  useEffect(() => {
    let alive = true;
    guildizerApi.get(`/api/guilds/${guildId}/team`)
      .then(({ data }) => { if (alive) setRole(data?.your_role || 'manager'); })
      .catch(() => { if (alive) setRole('manager'); });
    return () => { alive = false; };
  }, [guildId]);

  const api = useMemo(() => ({
    overview: (p) => wsApi.overview(guildId, p),
    campaigns: (p) => wsApi.campaigns(guildId, p),
    queue: (p) => wsApi.queue(guildId, p),
    summary: (id, p) => wsApi.summary(guildId, id, p),
    activity: (id) => wsApi.activity(guildId, id),
    get: (id) => eng.get(guildId, id).then((r) => ({ ...r, data: { campaign: r.data } })),
    update: (id, body) => eng.update(guildId, id, body),
    review: (cid, sid, body) => eng.reviewSubmission(guildId, cid, sid, body).catch(normalizeStale),
  }), [guildId]);

  const base = `/guildizer/servers/${guildId}`;
  const paths = {
    group: `${base}?tab=Engagement&sub=Campaigns`,
    overview: `${base}/campaigns`,
    list: `${base}/campaigns/all`,
    review: `${base}/campaigns/review`,
    create: (type) => `${base}/campaigns/new${type ? `?type=${type}` : ''}`,
    detail: (id, tab) => `${base}/campaigns/${id}${tab ? `?tab=${tab}` : ''}`,
    crm: `${base}?tab=Members`,
    home: '/guildizer', homeLabel: 'My servers',
  };
  const g = info.guild;
  const isPaid = !!g?.is_pro;
  const value = {
    platform: 'discord', noun: 'server', postName: 'Discord', idLabel: 'Discord ID', api, ui: discordUi,
    // Discord has no member drawer; the Members table (Analytics) is searchable by user id.
    memberPath: (userId) => (userId ? `/guildizer/servers/${guildId}?tab=Analytics&sub=Members&search=${encodeURIComponent(userId)}` : null),
    postUrl: (c) => (c.message_id && c.channel_id ? `https://discord.com/channels/${guildId}/${c.channel_id}/${c.message_id}` : null),
    planNote: (paid) => (paid
      ? 'Pro plan: multiple active campaigns, up to 25 tasks per campaign, X auto-verify, leaderboards and bulk export are available.'
      : 'Free plan: 1 active campaign, up to 3 tasks per campaign, manual/honor proof. Pro adds multiple campaigns, up to 25 tasks, X auto-verify, advanced fields, leaderboards and bulk export.'),
    botId: 'discord', rawBotId: null, groupId: guildId, isOfficial: false, paths, tick, bump,
    groupName: g?.name || null, group: g, tier: isPaid ? 'pro' : 'free', isPaid,
    role, isViewer: role === 'viewer', tz: browserTz(), ready: !info.loading && !info.error, loadError: info.error,
    channels: (g?.channels || []).filter((c) => TEXT_CHANNEL_TYPES.has(c.type)),
  };
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export default function GuildizerCampaignWorkspace({ view }) {
  return (
    <GuildizerWorkspaceProvider>
      <WorkspaceBody view={view} />
    </GuildizerWorkspaceProvider>
  );
}
