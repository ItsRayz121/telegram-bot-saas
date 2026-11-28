import React from 'react';

const URL_RE = /(https?:\/\/[^\s<>"']+)/gi;

/** Turn any http(s) URLs in a string into safe, clickable links (new tab). */
export function linkify(value) {
  const text = String(value ?? '');
  return text.split(URL_RE).map((part, i) => {
    if (i % 2 === 0) return part;
    // Trailing punctuation belongs to the sentence, not the link.
    const m = /[).,;:!?]+$/.exec(part);
    const url = m ? part.slice(0, m.index) : part;
    return (
      <React.Fragment key={i}>
        <a href={url} target="_blank" rel="noopener noreferrer"
          style={{ color: '#6ab0ff', textDecoration: 'underline', wordBreak: 'break-all' }}>{url}</a>
        {m ? m[0] : ''}
      </React.Fragment>
    );
  });
}

/** Filesystem-safe slug for download names. */
export function fileSlug(s, fallback = 'campaign') {
  const out = String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60);
  return out || fallback;
}
