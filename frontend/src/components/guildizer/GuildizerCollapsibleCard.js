import React from 'react';
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Box,
  Typography,
} from '@mui/material';
import { ExpandMore } from '@mui/icons-material';
import { useGuildizerUiPrefs } from '../../context/GuildizerUiPrefsContext';

/**
 * Guildizer settings card that collapses/expands like the existing accordions,
 * with per-user persisted open/closed state. Isolated copy of Telegizer's
 * CollapsibleCard (same API, Guildizer context).
 *
 * Props: id (required), title, badge, defaultOpen (default false), sx, children.
 */
export default function GuildizerCollapsibleCard({
  id,
  title,
  badge = null,
  action = null,
  defaultOpen = false,
  sx,
  children,
}) {
  const { ready, isOpen, toggle } = useGuildizerUiPrefs();
  const expanded = ready ? isOpen(id, defaultOpen) : false;
  return (
    <Accordion
      expanded={expanded}
      onChange={() => toggle(id, defaultOpen)}
      sx={{ mt: 2, ...sx }}
    >
      <AccordionSummary expandIcon={<ExpandMore />}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%', pr: 1 }}>
          {typeof title === 'string' ? (
            <Typography fontWeight={600}>{title}</Typography>
          ) : (
            title
          )}
          {badge}
          {action && (
            <Box
              sx={{ ml: 'auto', display: 'flex', alignItems: 'center' }}
              onClick={(e) => e.stopPropagation()}
              onFocus={(e) => e.stopPropagation()}
            >
              {action}
            </Box>
          )}
        </Box>
      </AccordionSummary>
      <AccordionDetails>{children}</AccordionDetails>
    </Accordion>
  );
}
