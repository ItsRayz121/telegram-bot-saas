import React from 'react';
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Box,
  Typography,
} from '@mui/material';
import { ExpandMore } from '@mui/icons-material';
import { useUiPrefs } from '../context/UiPrefsContext';

/**
 * A settings card that collapses/expands like the existing "Extended Rules" and
 * "Language Filter" accordions. Open/closed state is remembered per user (via
 * UiPrefsContext) so a refresh keeps it the way the user left it.
 *
 * Props:
 *   id          unique, stable key for this card (required)
 *   title       string or node shown in the header
 *   badge       optional node rendered after the title (e.g. a Pro badge)
 *   defaultOpen start expanded the very first time (default: false = closed)
 *   sx          forwarded to the Accordion
 *   children    the card body (shown when expanded)
 */
export default function CollapsibleCard({
  id,
  title,
  badge = null,
  defaultOpen = false,
  sx,
  children,
}) {
  const { ready, isOpen, toggle } = useUiPrefs();
  const expanded = ready ? isOpen(id, defaultOpen) : false;
  return (
    <Accordion
      expanded={expanded}
      onChange={() => toggle(id, defaultOpen)}
      sx={{ mt: 2, ...sx }}
    >
      <AccordionSummary expandIcon={<ExpandMore />}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {typeof title === 'string' ? (
            <Typography fontWeight={600}>{title}</Typography>
          ) : (
            title
          )}
          {badge}
        </Box>
      </AccordionSummary>
      <AccordionDetails>{children}</AccordionDetails>
    </Accordion>
  );
}
