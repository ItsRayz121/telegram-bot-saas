import React from 'react';
import { Box, Typography, Chip, Card, CardContent } from '@mui/material';
import { PALETTE } from '../theme';

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

        {/* Icon orb */}
        <Box
          sx={{
            width: 84,
            height: 84,
            borderRadius: 4,
            background: PALETTE.bg3,
            border: `1px solid ${PALETTE.border2}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            mx: 'auto',
            mb: 3,
          }}
        >
          {Icon && <Icon sx={{ fontSize: 36, color: PALETTE.text2 }} />}
        </Box>

        {/* Badge */}
        <Chip
          label="Coming Soon"
          size="small"
          sx={{
            mb: 2.5,
            background: PALETTE.bg3,
            color: PALETTE.text2,
            border: `1px solid ${PALETTE.border2}`,
            fontWeight: 500,
            fontSize: '0.75rem',
          }}
        />

        {/* Title */}
        <Typography variant="h4" fontWeight={600} mb={1.5} letterSpacing="-0.025em">
          {title}
        </Typography>

        {/* Subtitle */}
        <Typography variant="body1" color="text.secondary" mb={4} sx={{ lineHeight: 1.75 }}>
          {subtitle}
        </Typography>

        {/* Feature preview cards */}
        {features.length > 0 && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, textAlign: 'left' }}>
            {features.map((f) => (
              <Card
                key={f.title || f.label || f.name}
                sx={{
                  border: '1px dashed',
                  borderColor: PALETTE.border2,
                  background: 'transparent',
                }}
              >
                <CardContent sx={{ py: 1.5, px: 2, '&:last-child': { pb: 1.5 } }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                    {f.icon && (
                      <Box sx={{
                        width: 32, height: 32, borderRadius: '8px', flexShrink: 0,
                        background: PALETTE.bg3, border: `1px solid ${PALETTE.border1}`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}>
                        <f.icon sx={{ fontSize: 16, color: PALETTE.text2 }} />
                      </Box>
                    )}
                    <Box>
                      <Typography fontSize="0.875rem" fontWeight={500} color="text.primary">
                        {f.title}
                      </Typography>
                      {f.desc && (
                        <Typography fontSize="0.8125rem" color="text.secondary">
                          {f.desc}
                        </Typography>
                      )}
                    </Box>
                    <Chip
                      label="Soon"
                      size="small"
                      sx={{
                        ml: 'auto', height: 20, fontSize: '0.75rem', fontWeight: 500,
                        bgcolor: 'transparent', color: 'text.secondary',
                        border: `1px solid ${PALETTE.border1}`,
                      }}
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
