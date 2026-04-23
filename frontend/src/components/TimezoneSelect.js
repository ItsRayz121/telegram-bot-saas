import React from 'react';
import { Autocomplete, TextField } from '@mui/material';

export const TIMEZONES = [
  'UTC',
  // Americas
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Anchorage',
  'America/Toronto',
  'America/Vancouver',
  'America/Mexico_City',
  'America/Bogota',
  'America/Lima',
  'America/Sao_Paulo',
  'America/Argentina/Buenos_Aires',
  'America/Santiago',
  'America/Caracas',
  'America/Halifax',
  'America/Havana',
  'America/Panama',
  // Europe
  'Europe/London',
  'Europe/Dublin',
  'Europe/Lisbon',
  'Europe/Paris',
  'Europe/Berlin',
  'Europe/Madrid',
  'Europe/Rome',
  'Europe/Amsterdam',
  'Europe/Brussels',
  'Europe/Stockholm',
  'Europe/Vienna',
  'Europe/Warsaw',
  'Europe/Prague',
  'Europe/Budapest',
  'Europe/Bucharest',
  'Europe/Athens',
  'Europe/Helsinki',
  'Europe/Kiev',
  'Europe/Minsk',
  'Europe/Moscow',
  'Europe/Istanbul',
  // Africa
  'Africa/Cairo',
  'Africa/Lagos',
  'Africa/Nairobi',
  'Africa/Johannesburg',
  'Africa/Casablanca',
  'Africa/Abidjan',
  'Africa/Accra',
  // Asia
  'Asia/Dubai',
  'Asia/Muscat',
  'Asia/Karachi',
  'Asia/Kolkata',
  'Asia/Colombo',
  'Asia/Kathmandu',
  'Asia/Dhaka',
  'Asia/Yangon',
  'Asia/Bangkok',
  'Asia/Ho_Chi_Minh',
  'Asia/Jakarta',
  'Asia/Singapore',
  'Asia/Kuala_Lumpur',
  'Asia/Manila',
  'Asia/Shanghai',
  'Asia/Hong_Kong',
  'Asia/Taipei',
  'Asia/Seoul',
  'Asia/Tokyo',
  'Asia/Riyadh',
  'Asia/Baghdad',
  'Asia/Tehran',
  'Asia/Kabul',
  'Asia/Tashkent',
  'Asia/Almaty',
  'Asia/Yekaterinburg',
  'Asia/Novosibirsk',
  'Asia/Vladivostok',
  // Australia / Pacific
  'Australia/Perth',
  'Australia/Darwin',
  'Australia/Adelaide',
  'Australia/Brisbane',
  'Australia/Sydney',
  'Australia/Melbourne',
  'Pacific/Auckland',
  'Pacific/Fiji',
  'Pacific/Honolulu',
  'Pacific/Guam',
];

export default function TimezoneSelect({ value, onChange, label = 'Timezone', size = 'small', fullWidth = true, sx }) {
  return (
    <Autocomplete
      value={value || 'UTC'}
      options={TIMEZONES}
      onChange={(_, newValue) => onChange(newValue || 'UTC')}
      renderInput={(params) => (
        <TextField {...params} label={label} size={size} fullWidth={fullWidth} sx={sx} />
      )}
      disableClearable
      size={size}
      fullWidth={fullWidth}
      sx={sx}
    />
  );
}

/**
 * Format a UTC ISO string (as returned by the backend with trailing Z)
 * into a human-readable string in the given IANA timezone.
 */
export function formatInTimezone(utcIsoStr, tz) {
  if (!utcIsoStr) return '—';
  try {
    const iso = utcIsoStr.includes('+') || utcIsoStr.endsWith('Z')
      ? utcIsoStr
      : utcIsoStr + 'Z';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return utcIsoStr;
    return d.toLocaleString('en-GB', {
      timeZone: tz || 'UTC',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  } catch {
    return utcIsoStr;
  }
}
