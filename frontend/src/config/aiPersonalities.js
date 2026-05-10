/**
 * AI Personality display config — mirrors backend bot_features/ai_personality.py.
 *
 * When adding a new personality on the backend, add a matching entry here.
 * This file is display-only: actual prompts live on the backend.
 */

export const AI_PERSONALITIES = [
  {
    id: "professional_support",
    label: "Professional Customer Support",
    description: "Calm, concise, trusted support-agent feel. Best for SaaS, services, and product communities.",
    emoji: "💼",
  },
  {
    id: "friendly_community",
    label: "Friendly Community Moderator",
    description: "Warm, conversational, community-first. Best for hobby groups, fan communities, and welcoming servers.",
    emoji: "🤝",
  },
  {
    id: "enterprise_assistant",
    label: "Serious Enterprise Assistant",
    description: "Premium, highly professional, minimal emojis, structured. Best for financial, legal, and B2B communities.",
    emoji: "🏢",
  },
  {
    id: "web3_moderator",
    label: "Web3 Community Manager",
    description: "Crypto-native tone, ecosystem-focused, educational but casual. Best for crypto and Web3 projects.",
    emoji: "⛓️",
  },
  {
    id: "gaming_community",
    label: "Gaming / Fun Community",
    description: "Energetic, playful, meme-aware, shorter replies. Best for gaming servers and fun communities.",
    emoji: "🎮",
  },
  {
    id: "technical_assistant",
    label: "Technical Documentation Assistant",
    description: "Precise, accurate, structured. Best for developer communities, open-source projects, and API docs.",
    emoji: "🛠️",
  },
  {
    id: "creator_community",
    label: "Creator / Fan Community Assistant",
    description: "Supportive, creator-focused, engagement-oriented. Best for content creator and fan communities.",
    emoji: "🎨",
  },
];

export const REPLY_LENGTHS = [
  { value: "concise",  label: "Concise",  description: "1–2 sentences. Fast, direct." },
  { value: "balanced", label: "Balanced", description: "Matches complexity — default." },
  { value: "detailed", label: "Detailed", description: "Thorough, structured paragraphs." },
];

export const EMOJI_LEVELS = [
  { value: "none",     label: "None",     description: "Zero emojis in any reply." },
  { value: "minimal",  label: "Minimal",  description: "1 emoji max, only when it adds meaning." },
  { value: "moderate", label: "Moderate", description: "Natural emoji usage when appropriate." },
];

export const FORMALITY_LEVELS = [
  { value: "casual",  label: "Casual",  description: "Contractions, conversational phrasing." },
  { value: "neutral", label: "Neutral", description: "Personality-defined — balanced default." },
  { value: "formal",  label: "Formal",  description: "No contractions, complete formal sentences." },
];
