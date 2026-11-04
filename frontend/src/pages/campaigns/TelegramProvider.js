import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { engagement, engagementWs, settings } from '../../services/api';
import {
  CampaignEditDialog, CampaignManageDialog, CampaignWizard, PostStatusCell, ScreenshotViewer, TYPES, XKeyDialog,
} from '../../components/CampaignManager';
import { memberProfilePath } from '../../components/analytics/shared';
import { WorkspaceContext as Ctx, useWorkspace } from './common';

// Telegizer's side of the shared campaign workspace. Kept out of common.js so that light
// importers (CampaignsEntry, Guildizer's entry card) don't pull the big campaign forms in.
// Telegram forms, pre-bound to the current group. Stable component identities (no remounts).
function useTg() { const ws = useWorkspace(); return { botId: ws.botId, groupId: ws.groupId }; }
function TgWizard(p) { return <CampaignWizard {...useTg()} {...p} />; }
function TgManage(p) { return <CampaignManageDialog {...useTg()} {...p} />; }
function TgEdit(p) { return <CampaignEditDialog {...useTg()} {...p} />; }
function TgPostStatus(p) { return <PostStatusCell {...useTg()} {...p} />; }
function TgScreenshot({ s }) { return <ScreenshotViewer {...useTg()} campaignId={s.campaign_id} submissionId={s.id} />; }
const telegramUi = { TYPES, Wizard: TgWizard, Manage: TgManage, Edit: TgEdit, PostStatus: TgPostStatus, Screenshot: TgScreenshot, XKeyDialog };

function telegramPostUrl(group, campaign) {
  if (!campaign.telegram_message_id || !group) return null;
  if (group.username) return `https://t.me/${String(group.username).replace(/^@/, '')}/${campaign.telegram_message_id}`;
  const id = String(group.telegram_group_id || '');
  return id.startsWith('-100') ? `https://t.me/c/${id.slice(4)}/${campaign.telegram_message_id}` : null;
}

export function WorkspaceProvider({ children }) {
  const { id: rawBotId, groupId } = useParams();
  const botId = rawBotId || 'official';
  const isOfficial = !rawBotId;
  const [info, setInfo] = useState({ loading: true, error: null, group: null, tier: 'free', role: null, tz: 'UTC' });
  const [tick, setTick] = useState(0);              // bumped after changes so every view refetches
  const bump = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setInfo((i) => ({ ...i, loading: true, error: null }));
    settings.getGroupSettings(botId, groupId)
      .then((r) => {
        if (cancelled) return;
        const g = r.data.group || {};
        setInfo({
          loading: false, error: null, group: g,
          tier: r.data.owner_plan || 'free', role: r.data.access_role || null,
          tz: r.data.timezone || g.timezone || 'UTC',
        });
      })
      .catch((e) => { if (!cancelled) setInfo((i) => ({ ...i, loading: false, error: e?.response?.status === 404 ? 'This group was not found or you do not have access.' : 'Could not load this group.' })); });
    return () => { cancelled = true; };
  }, [botId, groupId]);

  const base = isOfficial ? `/groups/${groupId}` : `/bot/${rawBotId}/group/${groupId}`;
  const paths = {
    group: base,
    overview: `${base}/campaigns`,
    list: `${base}/campaigns/all`,
    review: `${base}/campaigns/review`,
    create: (type) => `${base}/campaigns/new${type ? `?type=${type}` : ''}`,
    detail: (id, tab) => `${base}/campaigns/${id}${tab ? `?tab=${tab}` : ''}`,
    crm: `${base}/crm`,
  };
  const api = useMemo(() => ({
    overview: (p) => engagementWs.overview(botId, groupId, p),
    campaigns: (p) => engagementWs.campaigns(botId, groupId, p),
    queue: (p) => engagementWs.queue(botId, groupId, p),
    summary: (id, p) => engagementWs.summary(botId, groupId, id, p),
    activity: (id) => engagementWs.activity(botId, groupId, id),
    get: (id) => engagement.get(botId, groupId, id),                       // -> { data: { campaign } }
    update: (id, body) => engagement.update(botId, groupId, id, body),
    review: (cid, sid, body) => engagement.reviewSubmission(botId, groupId, cid, sid, body),
  }), [botId, groupId]);
  const value = {
    platform: 'telegram', noun: 'group', postName: 'Telegram', idLabel: 'Telegram ID', api, ui: telegramUi,
    memberPath: (userId) => memberProfilePath({ isOfficial, botId: rawBotId, groupId, userId }),
    postUrl: (c) => telegramPostUrl(info.group, c),
    planNote: (isPaid, tier) => (isPaid
      ? `${tier.charAt(0).toUpperCase()}${tier.slice(1)} plan: multiple campaigns, multi-task campaigns, link checks, winner picker and bulk export are available.`
      : 'Free plan: 1 active campaign, manual/honor proof, Telegram-join auto-verify. Pro adds multiple campaigns, link checks, advanced fields, winner picker and bulk export.'),
    botId, rawBotId, groupId, isOfficial, paths, tick, bump,
    groupName: info.group?.title || info.group?.group_name || info.group?.name || null,
    group: info.group, tier: info.tier, isPaid: info.tier && info.tier !== 'free',
    role: info.role, isViewer: info.role === 'viewer', tz: info.tz, ready: !info.loading, loadError: info.error,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

