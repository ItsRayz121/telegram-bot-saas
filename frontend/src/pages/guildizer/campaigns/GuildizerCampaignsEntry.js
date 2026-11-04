import React from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { Box, Button, Card, CardContent, Typography } from '@mui/material';
import { guildizerCampaignWorkspace as wsApi } from '../../../services/guildizerApi';
import { usePolled } from '../../campaigns/common';
import { StatGrid, StatTile } from '../../../components/analytics/shared';

/** Engagement > Campaigns: headline numbers + links into the routed campaign workspace (mirrors Telegizer's CampaignsEntry). */
export default function GuildizerCampaignsEntry({ guildId }) {
  const base = `/guildizer/servers/${guildId}/campaigns`;
  const { data, loading, error } = usePolled(() => wsApi.overview(guildId, { days: 7 }), [guildId], { intervalMs: 0 });
  const t = data?.totals;
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" fontWeight={700} component="h2">Engagement campaigns</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Run social tasks, content submissions, giveaways, raids and proof collection. Campaigns have their own workspace
          with an overview, a campaign list, a review queue and exports. Raids are a campaign type, so they live here too.
        </Typography>
        {error && !data ? (
          <Typography variant="body2" color="error">Couldn't load the campaign summary. You can still open the workspace.</Typography>
        ) : (
          <StatGrid min={150}>
            <StatTile label="Active campaigns" value={t?.active_campaigns} loading={loading && !data} />
            <StatTile label="Pending review" value={t?.pending_review} loading={loading && !data} tone={t?.pending_review ? 'warning.main' : undefined} />
            <StatTile label="Approved submissions" value={t?.approved_submissions} loading={loading && !data} />
          </StatGrid>
        )}
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Button variant="contained" component={RouterLink} to={base}>Open campaign workspace</Button>
          <Button variant="outlined" component={RouterLink} to={`${base}/review`}>Review queue{t?.pending_review ? ` (${t.pending_review})` : ''}</Button>
          <Button variant="outlined" component={RouterLink} to={`${base}/new`}>New campaign</Button>
        </Box>
      </CardContent>
    </Card>
  );
}
