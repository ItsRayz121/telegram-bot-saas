import React from 'react';

// Signal-tower illustration. Inline SVG + CSS only: bundled with the app (and duplicated
// in public/offline.html, which the service worker precaches), so it renders with zero
// network access.
const CSS = `
.tg-off-glow{animation:tgOffGlow 2.6s ease-in-out infinite}
.tg-off-ring{transform-box:fill-box;transform-origin:center;animation:tgOffRing 3.2s ease-out infinite;opacity:0}
.tg-off-ring.r2{animation-delay:1.05s}.tg-off-ring.r3{animation-delay:2.1s}
.tg-off-star{animation:tgOffTwinkle 5s ease-in-out infinite}
@keyframes tgOffGlow{0%,100%{opacity:.55}50%{opacity:1}}
@keyframes tgOffRing{0%{transform:scale(.3);opacity:.9}100%{transform:scale(2.6);opacity:0}}
@keyframes tgOffTwinkle{0%,100%{opacity:.2}50%{opacity:.9}}
@media (prefers-reduced-motion:reduce){.tg-off-glow,.tg-off-ring,.tg-off-star{animation:none!important}.tg-off-ring{opacity:.35}}
`;

const STARS = [[40, 60, 0], [320, 48, 1.2], [70, 140, 2.4], [300, 130, 0.6], [250, 24, 1.8]];

export default function OfflineArt({ size = 340 }) {
  return (
    <svg width={size} height={size * (300 / 360)} viewBox="0 0 360 300" role="img" aria-label="Signal tower searching for a connection" xmlns="http://www.w3.org/2000/svg" style={{ maxWidth: '100%', height: 'auto', overflow: 'visible' }}>
      <style>{CSS}</style>
      <defs>
        <linearGradient id="tgoStr" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#9db8ff" /><stop offset="1" stopColor="#4b3fd0" /></linearGradient>
        <linearGradient id="tgoAcc" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#5b8cff" /><stop offset="1" stopColor="#c084fc" /></linearGradient>
        <radialGradient id="tgoGlow"><stop offset="0" stopColor="#7aa2ff" stopOpacity=".6" /><stop offset="1" stopColor="#7aa2ff" stopOpacity="0" /></radialGradient>
        <linearGradient id="tgoFloor" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#5b8cff" stopOpacity="0" /><stop offset="1" stopColor="#5b8cff" stopOpacity=".35" /></linearGradient>
        <linearGradient id="tgoFadeG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#fff" /><stop offset="1" stopColor="#000" /></linearGradient>
        <mask id="tgoFade"><rect x="-80" y="224" width="520" height="76" fill="url(#tgoFadeG)" /></mask>
      </defs>
      <g fill="#cfd8ff">
        {STARS.map(([x, y, d]) => <circle key={x} className="tg-off-star" style={{ animationDelay: `${d}s` }} cx={x} cy={y} r="1.1" />)}
      </g>
      <g mask="url(#tgoFade)" stroke="#5b8cff" strokeOpacity=".5" strokeWidth="1" fill="none">
        <path d="M-80 232H440M-80 246H440M-80 264H440M-80 288H440" />
        <path d="M180 224L-60 300M180 224L10 300M180 224L90 300M180 224L180 300M180 224L270 300M180 224L350 300M180 224L420 300" />
      </g>
      <ellipse cx="180" cy="228" rx="90" ry="12" fill="url(#tgoFloor)" />
      <g transform="translate(180 62)">
        <circle r="60" fill="url(#tgoGlow)" className="tg-off-glow" />
        <circle className="tg-off-ring" r="24" fill="none" stroke="#7aa2ff" strokeWidth="1.6" />
        <circle className="tg-off-ring r2" r="24" fill="none" stroke="#a78bfa" strokeWidth="1.6" />
        <circle className="tg-off-ring r3" r="24" fill="none" stroke="#c084fc" strokeWidth="1.4" />
      </g>
      <g stroke="url(#tgoStr)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" fill="none">
        <path d="M180 66L142 228M180 66L218 228" />
        <path d="M168.4 119H191.6M160.8 153H199.2M153.5 187H206.5M146 221H214" />
        <path d="M168.4 119L199.2 153M191.6 119L160.8 153M160.8 153L206.5 187M199.2 153L153.5 187M153.5 187L214 221M206.5 187L146 221" strokeWidth="1.4" strokeOpacity=".7" />
      </g>
      <path d="M132 228h96" stroke="#7aa2ff" strokeWidth="3" strokeLinecap="round" />
      <circle cx="180" cy="62" r="7" fill="#0b1030" stroke="url(#tgoAcc)" strokeWidth="2.4" />
      <circle className="tg-off-glow" cx="180" cy="62" r="2.8" fill="#c4b5fd" />
      <path d="M180 55V44" stroke="url(#tgoStr)" strokeWidth="2.4" strokeLinecap="round" />
      <g className="tg-off-glow"><rect x="228" y="108" width="78" height="26" rx="13" fill="#0e1538" stroke="#5b8cff" strokeOpacity=".4" /><circle cx="244" cy="121" r="4" fill="#ef4444" /><rect x="254" y="118" width="40" height="6" rx="3" fill="#7e8bd8" opacity=".6" /></g>
      <g className="tg-off-glow" style={{ animationDelay: '1.2s' }}><rect x="54" y="148" width="64" height="26" rx="13" fill="#0e1538" stroke="#a78bfa" strokeOpacity=".4" /><circle cx="70" cy="161" r="4" fill="#f59e0b" /><rect x="80" y="158" width="28" height="6" rx="3" fill="#7e8bd8" opacity=".6" /></g>
    </svg>
  );
}
