/**
 * Centralized support configuration.
 * To switch support email, update SUPPORT_EMAIL only — nothing else changes.
 */

export const SUPPORT_EMAIL = 'fazalelahi5577@gmail.com';

export const SUPPORT_MAILTO = `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent('Telegizer Support Request')}&body=${encodeURIComponent('Hi Telegizer team,\n\nI need help with:\n\n[describe your issue]\n\n---\nAccount email: ')}`;

export const SUPPORT_LINKS = {
  channel:   'https://t.me/telegizer',
  community: 'https://t.me/telegizer_community',
  email:     SUPPORT_MAILTO,
};
