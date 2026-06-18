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
  action = null,
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
      disableGutters
      elevation={0}
      sx={{
        mt: 2,
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 2,
        overflow: 'hidden',
        // Kill the default MUI accordion divider line + sibling-merge so an
        // expanded card never overlaps or fuses with the card above/below it.
        '&:before': { display: 'none' },
        '&.Mui-expanded': { mt: 2 },
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
