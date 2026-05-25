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
            borderRadius: '50%',
            background: `radial-gradient(circle, ${PALETTE.blue}22 0%, ${PALETTE.blue}08 70%)`,
            border: `1px solid ${PALETTE.blue}35`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            mx: 'auto',
            mb: 3,
            boxShadow: `0 0 32px ${PALETTE.glowBlue}`,
            animation: 'aiPulse 3s ease-in-out infinite',
          }}
        >
          {Icon && <Icon sx={{ fontSize: 38, color: PALETTE.blueLt }} />}
        </Box>

        {/* Badge */}
        <Chip
          label="Coming Soon"
          size="small"
          sx={{
            mb: 2.5,
            background: `linear-gradient(135deg, ${PALETTE.blue}20, ${PALETTE.purple}18)`,
            color: PALETTE.blueLt,
            border: `1px solid ${PALETTE.blue}40`,
            fontWeight: 700,
            fontSize: '0.68rem',
            letterSpacing: '0.08em',
          }}
        />

        {/* Title */}
        <Typography variant="h4" fontWeight={800} mb={1.5} letterSpacing="-0.025em">
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
                  opacity: 0.65, border: '1px dashed',
                  borderColor: PALETTE.border2,
                  background: 'transparent',
                  transition: 'opacity 0.2s, border-color 0.2s',
                  '&:hover': { opacity: 0.85, borderColor: `${PALETTE.blue}40` },
                }}
              >
                <CardContent sx={{ py: 1.5, px: 2, '&:last-child': { pb: 1.5 } }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                    {f.icon && (
                      <Box sx={{
                        width: 32, height: 32, borderRadius: 1.5, flexShrink: 0,
                        background: `${PALETTE.blue}12`, border: `1px solid ${PALETTE.blue}20`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}>
                        <f.icon sx={{ fontSize: 16, color: `${PALETTE.blue}99` }} />
                      </Box>
                    )}
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
                      sx={{
                        ml: 'auto', height: 18, fontSize: '0.6rem', fontWeight: 600,
                        bgcolor: 'rgba(255,255,255,0.05)', color: 'text.disabled',
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
