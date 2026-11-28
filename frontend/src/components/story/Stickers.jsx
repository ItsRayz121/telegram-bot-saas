import React from 'react';

// Hand-drawn sticker art for the landing story. Inline SVG so it renders identically on every OS
// (emoji would look different on iOS, Android and Windows). Each sticker has the thick white
// outline Telegram and Discord stickers use, so it reads as "someone sent a sticker".

const OUT = { stroke: '#fff', strokeWidth: 6, strokeLinejoin: 'round', paintOrder: 'stroke' };

function Face({ children, fill = '#f5c542' }) {
  return (
    <>
      <circle cx="60" cy="62" r="40" fill={fill} {...OUT} />
      {children}
    </>
  );
}

const ART = {
  // Admin leaving for dinner: a bowl of noodles with chopsticks and steam.
  dinner: (
    <>
      <path d="M38 22c-4 6 4 9 0 15M56 18c-4 6 4 9 0 15M74 22c-4 6 4 9 0 15" fill="none" stroke="#c9ccd3" strokeWidth="4" strokeLinecap="round" />
      <path d="M86 20 64 58M98 26 70 60" stroke="#b07a45" strokeWidth="6" strokeLinecap="round" {...{ paintOrder: 'stroke' }} />
      <path d="M18 58h84c0 26-18 44-42 44S18 84 18 58z" fill="#e8673c" {...OUT} />
      <path d="M30 58c6-8 12 4 18-4s12 4 18-4 12 4 18-4" fill="none" stroke="#f7d27a" strokeWidth="5" strokeLinecap="round" />
      <path d="M30 74h60" stroke="#c4502b" strokeWidth="4" strokeLinecap="round" />
    </>
  ),
  // A member getting worried: raised brows, open mouth, a sweat drop.
  worried: (
    <Face>
      <path d="M40 46l12-5M80 46l-12-5" stroke="#3b2a12" strokeWidth="4.5" strokeLinecap="round" />
      <circle cx="47" cy="58" r="5" fill="#3b2a12" />
      <circle cx="73" cy="58" r="5" fill="#3b2a12" />
      <ellipse cx="60" cy="80" rx="9" ry="11" fill="#3b2a12" />
      <path d="M93 30c6 9 8 14 4 18s-11 0-9-6c1-4 3-8 5-12z" fill="#6ec3f2" {...OUT} strokeWidth={4} />
    </Face>
  ),
  // Happy member after getting rewarded.
  party: (
    <>
      <Face>
        <path d="M42 56q6-8 12 0M66 56q6-8 12 0" fill="none" stroke="#3b2a12" strokeWidth="4.5" strokeLinecap="round" />
        <path d="M40 70q20 22 40 0z" fill="#3b2a12" />
      </Face>
      <rect x="14" y="14" width="9" height="9" rx="2" fill="#4a9ff5" transform="rotate(20 18 18)" />
      <rect x="96" y="18" width="9" height="9" rx="2" fill="#4cc38a" transform="rotate(-15 100 22)" />
      <circle cx="104" cy="96" r="5" fill="#eb5257" />
      <circle cx="16" cy="94" r="4" fill="#e2a336" />
    </>
  ),
  trophy: (
    <>
      <path d="M36 22h48v20c0 18-10 30-24 30S36 60 36 42z" fill="#f5c542" {...OUT} />
      <path d="M36 30H22c0 14 6 22 16 22M84 30h14c0 14-6 22-16 22" fill="none" stroke="#f5c542" strokeWidth="6" />
      <path d="M52 72h16v14H52z" fill="#d9a520" {...OUT} strokeWidth={4} />
      <path d="M38 88h44v12H38z" fill="#8a5a2b" {...OUT} />
      <path d="M60 32l4 8 9 1-7 6 2 9-8-5-8 5 2-9-7-6 9-1z" fill="#fff6d1" />
    </>
  ),
  stopwatch: (
    <>
      <rect x="52" y="10" width="16" height="10" rx="3" fill="#c9ccd3" {...OUT} strokeWidth={4} />
      <circle cx="60" cy="64" r="40" fill="#1f2024" {...OUT} />
      <circle cx="60" cy="64" r="32" fill="none" stroke="#323338" strokeWidth="4" />
      <path d="M60 64V38" stroke="#4cc38a" strokeWidth="6" strokeLinecap="round" />
      <path d="M60 64 76 74" stroke="#ececee" strokeWidth="5" strokeLinecap="round" />
      <circle cx="60" cy="64" r="5" fill="#ececee" />
    </>
  ),
  // Big beats, shown as a stamp over the chat.
  alert: (
    <>
      <path d="M60 10 112 102H8z" fill="#eb5257" {...OUT} />
      <path d="M60 42v30" stroke="#fff" strokeWidth="10" strokeLinecap="round" />
      <circle cx="60" cy="87" r="6" fill="#fff" />
    </>
  ),
  late: (
    <>
      <path d="M60 6l12 22 24-10-4 26 24 8-20 16 14 22-26-2-4 26-20-18-20 18-4-26-26 2 14-22L4 52l24-8-4-26 24 10z" fill="#eb5257" {...OUT} />
      <path d="M44 44l32 32M76 44 44 76" stroke="#fff" strokeWidth="9" strokeLinecap="round" />
    </>
  ),
  shield: (
    <>
      <path d="M60 8 102 22v32c0 28-18 48-42 58C36 102 18 82 18 54V22z" fill="#4a9ff5" {...OUT} />
      <path d="M40 58l14 14 28-30" fill="none" stroke="#fff" strokeWidth="9" strokeLinecap="round" strokeLinejoin="round" />
    </>
  ),
};

export default function Sticker({ art, size = 96 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" aria-hidden="true" style={{ display: 'block', overflow: 'visible', filter: 'drop-shadow(0 6px 10px rgba(0,0,0,0.35))' }}>
      {ART[art] || null}
    </svg>
  );
}
