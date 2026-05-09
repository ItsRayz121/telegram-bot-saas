#!/usr/bin/env node
/**
 * Generates frontend/public/og-image.png (1200x630) for Telegizer.
 * Renders a dark-premium SaaS Open Graph card via SVG → sharp → PNG.
 * Run: node scripts/generate-og-image.js
 */

const sharp = require('sharp');
const path  = require('path');
const fs    = require('fs');

const W = 1200;
const H = 630;

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">
  <defs>
    <!-- Background gradient: deep navy to dark blue-purple -->
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%"   stop-color="#050d1a"/>
      <stop offset="55%"  stop-color="#0a1628"/>
      <stop offset="100%" stop-color="#0d1020"/>
    </linearGradient>

    <!-- Blue glow behind logo -->
    <radialGradient id="glow1" cx="50%" cy="48%" r="38%">
      <stop offset="0%"   stop-color="#2563EB" stop-opacity="0.18"/>
      <stop offset="100%" stop-color="#2563EB" stop-opacity="0"/>
    </radialGradient>

    <!-- Purple accent glow (bottom-right) -->
    <radialGradient id="glow2" cx="90%" cy="85%" r="40%">
      <stop offset="0%"   stop-color="#7C3AED" stop-opacity="0.14"/>
      <stop offset="100%" stop-color="#7C3AED" stop-opacity="0"/>
    </radialGradient>

    <!-- Grid line pattern -->
    <pattern id="grid" width="60" height="60" patternUnits="userSpaceOnUse">
      <path d="M 60 0 L 0 0 0 60" fill="none" stroke="#ffffff" stroke-width="0.5" stroke-opacity="0.04"/>
    </pattern>

    <!-- Logo circle gradient -->
    <linearGradient id="logoGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%"   stop-color="#2563EB"/>
      <stop offset="100%" stop-color="#7C3AED"/>
    </linearGradient>

    <!-- Top border gradient -->
    <linearGradient id="topBorder" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%"   stop-color="#2563EB" stop-opacity="0"/>
      <stop offset="30%"  stop-color="#2563EB" stop-opacity="1"/>
      <stop offset="70%"  stop-color="#7C3AED" stop-opacity="1"/>
      <stop offset="100%" stop-color="#7C3AED" stop-opacity="0"/>
    </linearGradient>

    <!-- Feature pill gradient -->
    <linearGradient id="pillGrad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%"   stop-color="#1e3a5f"/>
      <stop offset="100%" stop-color="#2d1b69"/>
    </linearGradient>
  </defs>

  <!-- Base background -->
  <rect width="${W}" height="${H}" fill="url(#bg)"/>

  <!-- Grid overlay -->
  <rect width="${W}" height="${H}" fill="url(#grid)"/>

  <!-- Glow layers -->
  <rect width="${W}" height="${H}" fill="url(#glow1)"/>
  <rect width="${W}" height="${H}" fill="url(#glow2)"/>

  <!-- Outer border -->
  <rect x="1" y="1" width="${W-2}" height="${H-2}" fill="none"
        stroke="#ffffff" stroke-opacity="0.06" stroke-width="1" rx="0"/>

  <!-- Top accent border line -->
  <rect x="0" y="0" width="${W}" height="3" fill="url(#topBorder)"/>

  <!-- ─── Logo area (left side) ─── -->
  <!-- Circular logo background -->
  <circle cx="190" cy="265" r="72" fill="url(#logoGrad)" opacity="0.15"/>
  <circle cx="190" cy="265" r="64" fill="url(#logoGrad)" opacity="0.22"/>
  <circle cx="190" cy="265" r="56" fill="url(#logoGrad)"/>

  <!-- T letter in logo -->
  <text x="190" y="290" font-family="Arial Black, Arial, sans-serif"
        font-size="58" font-weight="900" fill="white" text-anchor="middle"
        letter-spacing="-2">T</text>

  <!-- Brand name — "Telegizer" -->
  <text x="190" y="372" font-family="Arial, Helvetica, sans-serif"
        font-size="22" font-weight="700" fill="#ffffff" text-anchor="middle"
        letter-spacing="3" opacity="0.9">TELEGIZER</text>

  <!-- ─── Right / center content ─── -->
  <!-- Small category label -->
  <rect x="310" y="195" width="240" height="30" rx="15"
        fill="#2563EB" fill-opacity="0.18" stroke="#2563EB" stroke-opacity="0.4" stroke-width="1"/>
  <text x="430" y="215" font-family="Arial, Helvetica, sans-serif"
        font-size="12" font-weight="600" fill="#60a5fa" text-anchor="middle"
        letter-spacing="2">TELEGRAM AUTOMATION</text>

  <!-- Main headline — line 1 -->
  <text x="310" y="282" font-family="Arial Black, Arial, sans-serif"
        font-size="48" font-weight="900" fill="#ffffff" text-anchor="start"
        letter-spacing="-1.5">All-in-One Telegram</text>

  <!-- Main headline — line 2 -->
  <text x="310" y="340" font-family="Arial Black, Arial, sans-serif"
        font-size="48" font-weight="900" fill="url(#logoGrad)" text-anchor="start"
        letter-spacing="-1.5">Community Management</text>

  <!-- Subheadline / tagline -->
  <text x="310" y="385" font-family="Arial, Helvetica, sans-serif"
        font-size="20" font-weight="400" fill="#94a3b8" text-anchor="start">
    AutoMod · Scheduling · Analytics · AI · Member CRM
  </text>

  <!-- ─── Feature pills row ─── -->
  <!-- Pill 1 -->
  <rect x="310" y="420" width="130" height="34" rx="17"
        fill="#1e3a5f" stroke="#2563EB" stroke-opacity="0.5" stroke-width="1"/>
  <text x="375" y="442" font-family="Arial, Helvetica, sans-serif"
        font-size="12" font-weight="600" fill="#93c5fd" text-anchor="middle">Free Plan</text>

  <!-- Pill 2 -->
  <rect x="452" y="420" width="148" height="34" rx="17"
        fill="#1e3a5f" stroke="#2563EB" stroke-opacity="0.5" stroke-width="1"/>
  <text x="526" y="442" font-family="Arial, Helvetica, sans-serif"
        font-size="12" font-weight="600" fill="#93c5fd" text-anchor="middle">No Credit Card</text>

  <!-- Pill 3 -->
  <rect x="612" y="420" width="158" height="34" rx="17"
        fill="#2d1b69" stroke="#7C3AED" stroke-opacity="0.5" stroke-width="1"/>
  <text x="691" y="442" font-family="Arial, Helvetica, sans-serif"
        font-size="12" font-weight="600" fill="#c4b5fd" text-anchor="middle">300+ Cryptos</text>

  <!-- Pill 4 -->
  <rect x="782" y="420" width="148" height="34" rx="17"
        fill="#1e3a5f" stroke="#2563EB" stroke-opacity="0.5" stroke-width="1"/>
  <text x="856" y="442" font-family="Arial, Helvetica, sans-serif"
        font-size="12" font-weight="600" fill="#93c5fd" text-anchor="middle">5-Min Setup</text>

  <!-- ─── Bottom URL strip ─── -->
  <rect x="0" y="588" width="${W}" height="42" fill="#000000" fill-opacity="0.35"/>
  <text x="310" y="615" font-family="Arial, Helvetica, sans-serif"
        font-size="15" font-weight="400" fill="#64748b" text-anchor="start"
        letter-spacing="0.5">telegizer.com</text>

  <!-- Decorative dots (top-right) -->
  <circle cx="1060" cy="80"  r="3" fill="#2563EB" opacity="0.6"/>
  <circle cx="1090" cy="80"  r="3" fill="#7C3AED" opacity="0.6"/>
  <circle cx="1120" cy="80"  r="3" fill="#2563EB" opacity="0.6"/>
  <circle cx="1060" cy="110" r="3" fill="#7C3AED" opacity="0.4"/>
  <circle cx="1090" cy="110" r="3" fill="#2563EB" opacity="0.4"/>
  <circle cx="1120" cy="110" r="3" fill="#7C3AED" opacity="0.4"/>
  <circle cx="1060" cy="140" r="3" fill="#2563EB" opacity="0.25"/>
  <circle cx="1090" cy="140" r="3" fill="#7C3AED" opacity="0.25"/>
  <circle cx="1120" cy="140" r="3" fill="#2563EB" opacity="0.25"/>

  <!-- Vertical separator line -->
  <line x1="270" y1="180" x2="270" y2="470"
        stroke="#ffffff" stroke-opacity="0.07" stroke-width="1"/>
</svg>`;

const outPath = path.join(__dirname, '..', 'public', 'og-image.png');

sharp(Buffer.from(svg))
  .png({ quality: 95, compressionLevel: 8 })
  .toFile(outPath)
  .then(info => {
    console.log(`[og-image] Written → ${outPath}`);
    console.log(`[og-image] Size: ${(fs.statSync(outPath).size / 1024).toFixed(1)} KB  |  ${info.width}x${info.height}`);
  })
  .catch(err => {
    console.error('[og-image] Error:', err.message);
    process.exit(1);
  });
