import React from 'react';
import { Box, Chip, Typography, Tooltip } from '@mui/material';

// Quick-add preset chips for the AutoMod banned-words box. Clicking a chip calls
// onAdd(words) with that pack's word list; the parent merges them (deduped) into
// its own banned-words state. Shared by Telegizer (Telegram) and Guildizer (Discord).
export default function BlockedWordPresets({ packs, onAdd, sx }) {
  if (!packs?.length) return null;
  return (
    <Box sx={{ mt: 1.25, ...sx }}>
      <Typography variant="caption" color="text.secondary" display="block" mb={0.75}>
        Quick-add preset packs — click to append. Conservative scam/spam phrases only;
        edit or remove any word after adding.
      </Typography>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75 }}>
        {packs.map((p) => (
          <Tooltip
            key={p.key}
            arrow
            title={`${p.words.length} words · ${p.words.slice(0, 6).join(', ')}…`}
          >
            <Chip
              label={`${p.emoji} ${p.label}`}
              size="small"
              variant="outlined"
              onClick={() => onAdd(p.words)}
              sx={{ cursor: 'pointer' }}
            />
          </Tooltip>
        ))}
      </Box>
    </Box>
  );
}
