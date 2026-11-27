#!/usr/bin/env node
/**
 * Generates frontend/public/og-image.png (1200x630) and the app icons from the flat
 * Telegizer mark. Graphite background, one accent, the product shown as a chat log.
 * Run: node scripts/generate-og-image.js
 */
const sharp = require('sharp');
const path = require('path');

const PUB = path.join(__dirname, '..', 'public');
const BG = '#0f1012';
const CARD = '#18191c';
const LINE = '#2a2b30';
const TEXT = '#ececee';
const MUTED = '#909299';
const ACCENT = '#4a9ff5';
const RED = '#eb5257';

// The mark in a 24-unit box, scaled and positioned by the caller.
const mark = (x, y, s, color = ACCENT) => `
  <g transform="translate(${x} ${y}) scale(${s / 24})">
    <path d="M21.2 2.8 4.6 9.6l6.1 2.3 2.4 6.3 8.1-15.4Z" fill="${color}"/>
    <path d="m21.2 2.8-10.5 9.1" stroke="${BG}" stroke-opacity="0.45" stroke-width="1.2" stroke-linecap="round"/>
    <path d="M2.5 15.5h4M4.5 19h3.5" stroke="${color}" stroke-width="1.8" stroke-linecap="round"/>
  </g>`;

const SANS = "'IBM Plex Sans', 'Segoe UI', Arial, sans-serif";
const MONO = "'IBM Plex Mono', Consolas, 'Courier New', monospace";

const log = (y, time, text, color = MUTED) => `
  <text x="700" y="${y}" font-family="${MONO}" font-size="19" fill="${MUTED}">${time}</text>
  <text x="772" y="${y}" font-family="${MONO}" font-size="19" fill="${color}">${text}</text>`;

const og = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630">
  <rect width="1200" height="630" fill="${BG}"/>
  ${mark(80, 78, 40)}
  <text x="132" y="108" font-family="${SANS}" font-size="30" font-weight="600" fill="${TEXT}">telegizer</text>
  <text x="80" y="268" font-family="${SANS}" font-size="58" font-weight="500" fill="${TEXT}" letter-spacing="-1.5">Run your Telegram</text>
  <text x="80" y="336" font-family="${SANS}" font-size="58" font-weight="500" fill="${TEXT}" letter-spacing="-1.5">group without</text>
  <text x="80" y="404" font-family="${SANS}" font-size="58" font-weight="500" fill="${TEXT}" letter-spacing="-1.5">living in it</text>
  <text x="80" y="540" font-family="${MONO}" font-size="20" fill="${MUTED}">AutoMod · scheduled posts · levels · analytics</text>
  <rect x="660" y="150" width="460" height="330" rx="18" fill="${CARD}" stroke="${LINE}"/>
  <line x1="660" y1="206" x2="1120" y2="206" stroke="${LINE}"/>
  <circle cx="694" cy="178" r="5" fill="#4cc38a"/>
  <text x="710" y="185" font-family="${MONO}" font-size="18" fill="${MUTED}">bot admin · Base Builders</text>
  ${log(260, '18:02', 'spam removed · muted 24h', RED)}
  ${log(310, '18:04', 'mira_k joined via invite')}
  ${log(360, '18:04', 'welcome message sent', TEXT)}
  ${log(410, '18:00', 'AMA reminder posted', TEXT)}
  ${log(460, '18:06', 'dan_ol reached level 5')}
</svg>`;

// App icon: the mark on a graphite tile (icons need a background on home screens).
const icon = (size, pad = 0.2) => {
  const s = size * (1 - pad * 2);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}">
    <rect width="${size}" height="${size}" rx="${size * 0.22}" fill="#131416"/>
    ${mark(size * pad, size * pad, s)}
  </svg>`;
};

async function main() {
  await sharp(Buffer.from(og)).png({ compressionLevel: 9 }).toFile(path.join(PUB, 'og-image.png'));
  const jobs = [
    ['icons/telegizer-icon-512.png', 512], ['icons/telegizer-icon-192.png', 192], ['icons/telegizer-icon.png', 512],
    ['icons/apple-touch-icon.png', 180], ['icons/favicon-32.png', 32], ['icons/favicon-16.png', 16],
  ];
  for (const [file, size] of jobs) {
    await sharp(Buffer.from(icon(size, size <= 32 ? 0.12 : 0.2))).png().toFile(path.join(PUB, file));
  }
  require('fs').writeFileSync(path.join(PUB, 'icons/icon.svg'), icon(512).replace(/\n\s*/g, ''));
  console.log('og-image.png and icons written');
}

main().catch((e) => { console.error(e); process.exit(1); });
