import React, { useEffect, useRef } from 'react';
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Box,
  Typography,
} from '@mui/material';
import { ExpandMore } from '@mui/icons-material';
import { useSearchParams } from 'react-router-dom';
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
  // Deep-link focus: ?focus=<id> auto-opens this card, scrolls to it and pulses
  // it briefly, so the AI Activity status chips (and other deep-links) can land
  // the user right on the relevant setting.
  const [params] = useSearchParams();
  const focused = params.get('focus') === id;
  const ref = useRef(null);
  useEffect(() => {
    if (focused && ref.current) {
      ref.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [focused]);

  const expanded = focused || (ready ? isOpen(id, defaultOpen) : false);
  return (
    <Accordion
      ref={ref}
      expanded={expanded}
      onChange={() => toggle(id, defaultOpen)}
      disableGutters
      elevation={0}
      sx={{
        mt: 2,
        border: '1px solid',
        borderColor: focused ? 'primary.main' : 'divider',
        borderRadius: 2,
        overflow: 'hidden',
        // Kill the default MUI accordion divider line + sibling-merge so an
        // expanded card never overlaps or fuses with the card above/below it.
        '&:before': { display: 'none' },
        '&.Mui-expanded': { mt: 2 },
        ...(focused ? {
          animation: 'gzPulse 1.2s ease-in-out 2',
          '@keyframes gzPulse': {
            '0%, 100%': { boxShadow: '0 0 0 0 rgba(157,108,247,0.0)' },
            '50%': { boxShadow: '0 0 0 4px rgba(157,108,247,0.45)' },
          },
        } : {}),
        ...sx,
      }}
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
