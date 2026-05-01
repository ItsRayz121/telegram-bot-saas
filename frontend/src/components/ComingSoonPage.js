// ComingSoonPage — reusable placeholder for temporarily hidden features.
// Temporarily hidden for future reactivation — no backend logic removed.
import React from 'react';
import { Box, Typography, Chip, Card, CardContent } from '@mui/material';

export default function ComingSoonPage({ icon: Icon, title, subtitle, features = [] }) {
  return (
    <Box
      sx={{
        minHeight: '70vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        p: { xs: 2, md: 4 },
      }}
    >
      <Box sx={{ maxWidth: 520, width: '100%', textAlign: 'center' }}>
        {/* Icon */}
        <Box
          sx={{
            width: 80,
            height: 80,
            borderRadius: '50%',
            bgcolor: 'rgba(37,99,235,0.12)',
            border: '1px solid rgba(37,99,235,0.25)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            mx: 'auto',
            mb: 3,
          }}
        >
          {Icon && <Icon sx={{ fontSize: 38, color: 'primary.light' }} />}
        </Box>

        {/* Badge */}
        <Chip
          label="Coming Soon"
          size="small"
          sx={{
            mb: 2,
            bgcolor: 'rgba(37,99,235,0.15)',
            color: 'primary.light',
            border: '1px solid rgba(37,99,235,0.35)',
            fontWeight: 700,
            fontSize: '0.7rem',
            letterSpacing: '0.06em',
          }}
        />

        {/* Title */}
        <Typography variant="h4" fontWeight={800} mb={1.5}>
          {title}
        </Typography>

        {/* Subtitle */}
        <Typography variant="body1" color="text.secondary" mb={4} sx={{ lineHeight: 1.7 }}>
          {subtitle}
        </Typography>

        {/* Feature preview cards */}
        {features.length > 0 && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, textAlign: 'left' }}>
            {features.map((f, i) => (
              <Card key={i} sx={{ opacity: 0.6, border: '1px dashed', borderColor: 'divider' }}>
                <CardContent sx={{ py: 1.5, px: 2, '&:last-child': { pb: 1.5 } }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                    {f.icon && <f.icon sx={{ fontSize: 20, color: 'text.disabled', flexShrink: 0 }} />}
                    <Box>
                      <Typography fontSize="0.85rem" fontWeight={600} color="text.secondary">
                        {f.title}
                      </Typography>
                      {f.desc && (
                        <Typography fontSize="0.75rem" color="text.disabled">
                          {f.desc}
                        </Typography>
                      )}
                    </Box>
                    <Chip
                      label="Soon"
                      size="small"
                      sx={{ ml: 'auto', height: 18, fontSize: '0.6rem', bgcolor: 'rgba(255,255,255,0.06)', color: 'text.disabled' }}
                    />
                  </Box>
                </CardContent>
              </Card>
            ))}
          </Box>
        )}
      </Box>
    </Box>
  );
}
