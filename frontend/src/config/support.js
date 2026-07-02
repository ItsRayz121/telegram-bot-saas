/**
 * Centralized support configuration.
 * To switch support email, update SUPPORT_EMAIL only — nothing else changes.
 */

export const SUPPORT_EMAIL = 'fazalelahi5577@gmail.com';

const SUBJECT = 'Telegizer Support Request';
const BODY    = 'Hi Telegizer team,\n\nI need help with:\n\n[describe your issue]\n\n---\nAccount email: ';

export const SUPPORT_MAILTO = `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(SUBJECT)}&body=${encodeURIComponent(BODY)}`;

/** Gmail compose URL — opens directly in Gmail without requiring a local mail app. */
const _gmailParams = new URLSearchParams({ view: 'cm', fs: '1', to: SUPPORT_EMAIL, su: SUBJECT, body: BODY });
export const SUPPORT_GMAIL_URL = `https://mail.google.com/mail/?${_gmailParams.toString()}`;

/**
 * Opens the Gmail compose window in a new tab, pre-filled to our single
 * support address. Pass a `subject` to categorize the enquiry (e.g.
 * "Bug Report", "Enterprise & Partnership") — the body stays the same.
 * Falls back to mailto: if the popup is blocked.
 */
export function openSupportEmail(subject = SUBJECT, body = BODY) {
  const params = new URLSearchParams({ view: 'cm', fs: '1', to: SUPPORT_EMAIL, su: subject, body });
  const gmailUrl = `https://mail.google.com/mail/?${params.toString()}`;
  const win = window.open(gmailUrl, '_blank', 'noopener,noreferrer');
  if (!win || win.closed || typeof win.closed === 'undefined') {
    // Popup was blocked — fall back to mailto
    window.location.href = `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }
}

export const SUPPORT_LINKS = {
  channel:   'https://t.me/telegizer',
  community: 'https://t.me/telegizer_community',
  email:     SUPPORT_GMAIL_URL,
};
