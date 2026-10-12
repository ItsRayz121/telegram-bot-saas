import React from 'react';

// Inline SVG + CSS only: bundled with the app (and duplicated in public/offline.html,
// which the service worker precaches), so it renders with zero network access.
const CSS = `
.tg-off-float{animation:tgOffFloat 6s ease-in-out infinite;transform-origin:50% 50%}
.tg-off-line{animation:tgOffLine 4s ease-in-out infinite;transform-origin:150px 96px}
.tg-off-wifi{animation:tgOffPulse 2.4s ease-in-out infinite}
.tg-off-wifi path:nth-child(2){animation-delay:.2s}.tg-off-wifi path:nth-child(3){animation-delay:.4s}
.tg-off-star{animation:tgOffTwinkle 5s ease-in-out infinite}
@keyframes tgOffFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}
@keyframes tgOffLine{0%,100%{transform:rotate(-1.5deg)}50%{transform:rotate(2deg)}}
@keyframes tgOffPulse{0%,100%{opacity:.35}50%{opacity:1}}
@keyframes tgOffTwinkle{0%,100%{opacity:.25}50%{opacity:.8}}
@media (prefers-reduced-motion:reduce){.tg-off-float,.tg-off-line,.tg-off-wifi,.tg-off-star{animation:none!important}}
`;

export default function OfflineArt({ size = 240 }) {
  return (
    <svg width={size} height={size * 0.8} viewBox="0 0 240 192" role="img" aria-label="Astronaut waiting for a signal" xmlns="http://www.w3.org/2000/svg">
      <style>{CSS}</style>
      <defs>
        <linearGradient id="tgOffMoon" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#4c4a8a" /><stop offset="1" stopColor="#25234a" /></linearGradient>
        <linearGradient id="tgOffSuit" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#f1f0ff" /><stop offset="1" stopColor="#c4c2ee" /></linearGradient>
        <linearGradient id="tgOffAccent" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#8b5cf6" /><stop offset="1" stopColor="#ec4899" /></linearGradient>
      </defs>
      {[[30, 30], [205, 24], [214, 92], [18, 100], [120, 14]].map(([x, y], i) => (
        <circle key={i} className="tg-off-star" style={{ animationDelay: `${i * 0.9}s` }} cx={x} cy={y} r={i % 2 ? 1.4 : 1} fill="#c7d2fe" />
      ))}
      <ellipse cx="120" cy="178" rx="92" ry="9" fill="#000" opacity=".25" />
      <path d="M32 176c4-30 36-44 88-44s84 14 88 44z" fill="url(#tgOffMoon)" />
      <circle cx="70" cy="160" r="5" fill="#1d1b3d" opacity=".5" /><circle cx="168" cy="166" r="4" fill="#1d1b3d" opacity=".5" />
      <g className="tg-off-float">
        {/* body */}
        <rect x="92" y="94" width="40" height="42" rx="16" fill="url(#tgOffSuit)" />
        <rect x="104" y="108" width="16" height="8" rx="3" fill="url(#tgOffAccent)" opacity=".9" />
        {/* legs resting on the moon */}
        <rect x="96" y="130" width="14" height="26" rx="7" fill="#b9b6e8" />
        <rect x="114" y="130" width="14" height="26" rx="7" fill="#aeabe0" />
        {/* helmet */}
        <circle cx="112" cy="76" r="22" fill="url(#tgOffSuit)" />
        <rect x="98" y="66" width="28" height="20" rx="10" fill="#1b1a3a" />
        <ellipse cx="108" cy="72" rx="6" ry="3" fill="#a5b4fc" opacity=".55" />
        {/* arm + rod */}
        <path d="M128 104c10-2 18-8 24-14" stroke="#d9d7f7" strokeWidth="8" strokeLinecap="round" fill="none" />
        <path d="M150 92L196 52" stroke="#8b8fc7" strokeWidth="2.5" strokeLinecap="round" />
      </g>
      {/* line + wifi bobber */}
      <g className="tg-off-line">
        <path d="M196 52c6 20 4 44-6 62" stroke="#a5b4fc" strokeWidth="1" fill="none" opacity=".8" />
      </g>
      <g className="tg-off-wifi" transform="translate(190 108)" fill="none" stroke="url(#tgOffAccent)" strokeWidth="2.4" strokeLinecap="round">
        <path d="M-9 -3a13 13 0 0 1 18 0" /><path d="M-5.5 1a8 8 0 0 1 11 0" /><path d="M-2 5a3 3 0 0 1 4 0" />
      </g>
      <circle cx="190" cy="116" r="2" fill="#ec4899" className="tg-off-wifi" />
    </svg>
  );
}
