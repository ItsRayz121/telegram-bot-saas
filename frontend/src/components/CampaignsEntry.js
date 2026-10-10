import React from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { Box, Button, Card, CardContent, Typography } from '@mui/material';
import { engagementWs } from '../services/api';
import { usePolled } from '../pages/campaigns/common';
import { StatGrid, StatTile } from './analytics/shared';

/** Entry point inside the group's Community tab: headline numbers + links into the campaign workspace. */
export default function CampaignsEntry({ botId, groupId, isOfficial }) {
  const base = isOfficial ? `/groups/${groupId}/campaigns` : `/bot/${botId}/group/${groupId}/campaigns`;
  const { data, loading, error } = usePolled(() => engagementWs.overview(botId, groupId, { days: 7 }), [botId, groupId], { intervalMs: 0 });
  const t = data?.totals;
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" fontWeight={700} component="h2">Engagement campaigns</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Run social tasks, content submissions, giveaways, raids and proof collection. Campaigns now have their own workspace with an overview, a campaign list, a review queue and exports.
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
