import React, { useEffect, useState } from 'react';
import { Alert, Collapse, Typography, Box } from '@mui/material';
import { Campaign, Warning, Security } from '@mui/icons-material';

/**
 * Top-of-app announcement banner.
 *
 * Fetches the newest live "banner" announcement the current user hasn't
 * dismissed (and hasn't opted out of), shows it once, and records the
 * dismissal server-side so it never reappears. Fails silently — a banner
 * error must never break the app shell.
 *
 * `api` is a notifications-style client exposing getBanner() / dismissBanner(id),
 * so the same component serves both Telegizer and Guildizer.
 */
export default function AnnouncementBanner({ api }) {
  const [banner, setBanner] = useState(null);
  const [open, setOpen] = useState(true);

  useEffect(() => {
    let alive = true;
    if (!api?.getBanner) return undefined;
    api.getBanner()
      .then((r) => { if (alive) setBanner(r.data?.banner || null); })
      .catch(() => {});
    return () => { alive = false; };
  }, [api]);

  if (!banner) return null;

  // Telegizer exposes `announcement_type`; Guildizer exposes `level`. Accept both.
  const level = banner.announcement_type || banner.level;
  const severity = level === 'critical' ? 'error'
    : level === 'warning' ? 'warning' : 'info';
  const Icon = severity === 'error' ? Security : severity === 'warning' ? Warning : Campaign;

  const dismiss = () => {
    setOpen(false);
    if (api?.dismissBanner) api.dismissBanner(banner.id).catch(() => {});
  };

  return (
    <Collapse in={open} onExited={() => setBanner(null)}>
      <Alert severity={severity} icon={<Icon fontSize="inherit" />} onClose={dismiss}
        sx={{ borderRadius: 0, alignItems: 'center' }}>
        <Box>
          <Typography variant="subtitle2" fontWeight={700} component="span">{banner.title}</Typography>
          {banner.body && (
            <Typography variant="body2" component="span" sx={{ ml: 1 }}>{banner.body}</Typography>
          )}
        </Box>
      </Alert>
    </Collapse>
  );
}
