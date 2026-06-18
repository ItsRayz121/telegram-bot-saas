// Curated "quick-add" blocked-word preset packs, shared by Telegizer (Telegram)
// and Guildizer (Discord) AutoMod. Clicking a pack chip appends its words into
// the banned-words box; admins can freely edit/remove afterwards.
//
// Design rules (keep them conservative on purpose):
//  • Block scam/spam *phrases*, never plain community vocabulary. In a real crypto
//    chat people legitimately say "wallet", "airdrop", "mint" — so we only list the
//    scam construction ("free airdrop", "validate wallet"), not the bare word.
//  • The matcher is leet/spacing-aware, so no need to add f r e e / fr33 variants.
//  • Default enforcement should stay on "delete", never auto-ban, so a false hit
//    is never catastrophic (anti-ban-safe).

// ── Shared baseline: generic scam / phishing / DM-bait common to every community ──
export const UNIVERSAL_PACK = {
  key: 'universal',
  emoji: '🛡️',
  label: 'Universal scam/spam',
  words: [
    'free nitro', 'nitro giveaway', 'claim your reward', 'you have been selected',
    'congratulations you won', 'dm to claim', 'dm me to claim', 'message me to claim',
    'click to claim', 'claim your prize', 'you are the lucky winner', 'free gift card',
    'gift card giveaway', 'limited time offer dm', 'earn $500 a day', 'work from home dm',
    'easy money dm', 'investment opportunity dm', 'double your money', 'guaranteed income',
    'click this link', 'verify your account here', 'account suspended click', 'login to claim',
    'add me on telegram', 'contact me on whatsapp', 'hit me up dm', 'dm for details',
    'free money', 'too good to be true offer',
  ],
};

// ─────────────────────────────── TELEGRAM PACKS ───────────────────────────────
export const TELEGRAM_PACKS = [
  UNIVERSAL_PACK,
  {
    key: 'crypto', emoji: '🪙', label: 'Crypto / Web3',
    words: [
      'free airdrop', 'claim airdrop', 'airdrop is live', 'free crypto', 'free mint',
      'free nft', 'presale whitelist dm', 'guaranteed profit', 'guaranteed returns',
      '100x guaranteed', '1000x gem', 'next 100x', 'pump signal', 'pump and dump',
      'vip pump group', 'moonshot guaranteed', 'seed phrase', 'recovery phrase',
      'private key', 'validate wallet', 'sync your wallet', 'wallet validation',
      'connect wallet to claim', 'metamask support', 'wallet support team',
      'elon giveaway', 'bitcoin doubler', 'double your btc', 'send eth get back',
      'crypto recovery expert',
    ],
  },
  {
    key: 'trading', emoji: '📈', label: 'Trading / Forex',
    words: [
      'forex signals', 'free signals', 'vip signals', 'signals group', 'copy my trades',
      'copy trading dm', 'account management dm', 'managed forex account', 'guaranteed pips',
      '95% win rate', 'recover lost funds', 'recovery expert dm', 'binary options dm',
      'expert trader dm', 'double your deposit', 'profit in 24 hours', 'withdraw guaranteed',
      'forex mentor dm', 'trade with me dm', 'fund manager dm', 'weekly roi',
      'daily profit guaranteed', 'risk free trade', 'no loss strategy', 'invest and earn dm',
    ],
  },
  {
    key: 'investment', emoji: '💸', label: 'Investment / Earn-online',
    words: [
      'investment manager dm', 'earn from home', 'make money online dm', 'passive income dm',
      'earn $1000 weekly', 'become a millionaire', 'financial freedom dm', 'mining investment',
      'hyip', 'ponzi', 'get rich quick', 'money flip', 'cash flip', 'instant payout dm',
      'legit money maker', 'real investor dm', 'profit within hours', 'refer and earn dm',
      'paid daily', 'no risk high return', 'join my team dm', 'work online earn',
      'easy income dm', 'guaranteed daily profit', 'start earning today dm',
    ],
  },
  {
    key: 'giveaway', emoji: '🎁', label: 'Giveaway / Airdrop spam',
    words: [
      'giveaway live', 'free giveaway', 'you won a giveaway', 'lucky winner', 'spin to win',
      'free gift dm', 'official giveaway dm', 'congratulations winner', 'claim before it ends',
      'limited slots dm', 'first 100 only', 'free voucher', 'redeem your code',
      'gift waiting for you', 'claim now link', 'exclusive drop dm', 'free reward claim',
      'dm to claim prize', 'you are selected winner', 'claim your free gift',
    ],
  },
  {
    key: 'nsfw', emoji: '🔞', label: 'Adult / NSFW spam',
    words: [
      'nudes dm', 'nude pics dm', 'send nudes', 'onlyfans leak', 'free onlyfans',
      'leaked content dm', '18+ content dm', 'adult content dm', 'hot singles',
      'meet singles near you', 'sex dating', 'hookup dm', 'cam girls', 'free cam',
      'my private album', 'check my profile for nudes', 'dm for content', 'selling content dm',
      'snapchat nudes', 'premium snap dm', 'sugar daddy', 'sugar baby wanted',
      'link in bio nudes', 'free nudes dm',
    ],
  },
  {
    key: 'gambling', emoji: '🎰', label: 'Betting / Gambling',
    words: [
      'betting tips', 'fixed matches', 'sure bet', 'guaranteed win bet', 'casino bonus dm',
      'free spins dm', 'gambling site dm', 'betting signals', 'match fixing dm',
      '100% sure odds', 'daily winning tips', 'predictions dm', 'aviator predictor',
      'hack betting', 'win every bet', 'free bet code', 'deposit bonus dm',
      'jackpot guaranteed', 'betting expert dm', 'fixed odds dm',
    ],
  },
  {
    key: 'shopping', emoji: '🛒', label: 'Deals / Shopping spam',
    words: [
      'free coupon', 'discount code dm', 'cheap deals dm', 'dm for price', 'wholesale dm',
      'dropship supplier dm', 'replica watches', 'replica bags', 'cheap iphone dm',
      'gift card cheap', 'buy followers', 'buy likes', 'cheap smm dm', 'smm panel dm',
      'best price dm', 'order now dm', 'limited stock dm', 'free shipping click',
      'deal of the day link', 'contact for catalog',
    ],
  },
  {
    key: 'piracy', emoji: '🎬', label: 'Piracy / Streaming',
    words: [
      'free netflix', 'netflix premium free', 'free premium account', 'cracked account dm',
      'mod apk dm', 'free subscription dm', 'streaming link dm', 'movie download link',
      'leaked movie dm', 'premium cookies dm', 'free spotify premium', 'hacked account dm',
      'account selling dm', 'cheap subscription dm', 'iptv subscription dm',
      'premium unlocked dm', 'dm for accounts', 'full movie link', 'free hbo', 'free disney plus',
    ],
  },
  {
    key: 'phishing', emoji: '🔐', label: 'Phishing / Account theft',
    words: [
      'verify your account', 'account will be suspended', 'confirm your password',
      'login here to verify', 'update your payment', 'your account is locked', 'click to unlock',
      'security alert click', 'telegram premium free', 'verify to avoid ban', 'official support dm',
      'admin support dm', 'send your otp', 'share your code', 'your parcel is waiting',
      'customs fee dm', 'confirm your identity link', 'reactivate account link',
      'suspicious login verify', 'claim your refund link',
    ],
  },
];

// ─────────────────────────────── DISCORD PACKS ───────────────────────────────
export const DISCORD_PACKS = [
  UNIVERSAL_PACK,
  {
    key: 'gaming', emoji: '🎮', label: 'Gaming',
    words: [
      'free vbucks', 'free robux', 'free skins', 'free fortnite skins', 'account generator',
      'free nitro generator', 'free aimbot', 'free cheats dm', 'undetected cheats dm',
      'boosting service dm', 'rank boost dm', 'selling account dm', 'buy account dm',
      'free game keys', 'free steam keys', 'cheap valorant points', 'modded account dm',
      'free coins generator', 'hack download dm', 'free gems generator', 'cheap boosting dm',
      'unban service dm', 'free spins generator', 'sell my account dm',
    ],
  },
  {
    key: 'nitro', emoji: '🎁', label: 'Nitro / Phishing scams',
    words: [
      'free nitro', 'nitro giveaway', 'claim free nitro', 'free discord nitro', 'steam gift',
      'free steam gift', 'nitro and a game', 'click to claim nitro', 'gift you nitro',
      'steamcommunity gift', 'qr login here', 'login to claim nitro', 'free nitro generator',
      'scan to verify', 'dm for free nitro', 'nitro for free here', 'gift dropped claim',
      'free nitro link', 'you received nitro', 'claim your gift here', 'free discord boosts',
      'verify with qr code',
    ],
  },
  {
    key: 'crypto', emoji: '🪙', label: 'Crypto / NFT',
    words: [
      'free airdrop', 'claim airdrop', 'free nft', 'free mint', 'whitelist spot dm',
      'presale dm', 'guaranteed 100x', 'pump group dm', 'seed phrase', 'recovery phrase',
      'private key', 'connect wallet to claim', 'validate wallet', 'wallet sync',
      'metamask support', 'free crypto giveaway', 'elon giveaway', 'mint is live free',
      'claim your nft', 'dm mod for whitelist', 'guaranteed profit', 'double your crypto',
      'crypto giveaway dm', 'wallet support team',
    ],
  },
  {
    key: 'creator', emoji: '🎬', label: 'Creator / Streamer',
    words: [
      'free followers', 'buy followers', 'free subs', 'sub4sub', 'view bot', 'cheap viewers',
      'free twitch followers', 'buy youtube subs', 'free likes', 'grow your channel dm',
      'promotion dm cheap', 'free discord members', 'server boost cheap dm', 'buy members',
      'f4f', 'follow for follow', 'free instagram followers', 'smm panel dm',
      'cheap engagement dm', 'free views bot',
    ],
  },
  {
    key: 'trading', emoji: '📈', label: 'Trading',
    words: [
      'forex signals', 'free signals', 'vip signals', 'copy my trades', 'account management dm',
      'guaranteed profit', 'recover lost funds', 'binary options dm', 'double your deposit',
      'fund manager dm', 'daily profit guaranteed', '95% win rate', 'dm to invest',
      'crypto mentor dm', 'profit in 24 hours', 'signals group dm', 'managed account dm',
      'guaranteed returns', 'pump signal', 'investment opportunity dm',
    ],
  },
  {
    key: 'dev', emoji: '💻', label: 'Tech / Dev',
    words: [
      'free vps dm', 'cracked software dm', 'free license key', 'nulled script dm',
      'free api key dm', 'leaked source dm', 'dm for cheap hosting', 'free domain dm',
      'cracked app dm', 'mod menu dm', 'free premium tool', 'license bypass dm',
      'free github copilot', 'free chatgpt plus', 'premium account dm', 'free proxy list dm',
      'dm for crack', 'selling accounts dm', 'free openai key', 'cracked license dm',
    ],
  },
  {
    key: 'nsfw', emoji: '🔞', label: 'NSFW / Adult spam',
    words: [
      'nudes dm', 'send nudes', 'onlyfans leak', 'free onlyfans', 'leaked content dm',
      '18+ dm', 'adult content dm', 'hot singles', 'hookup dm', 'cam girls',
      'my private album', 'check my profile', 'dm for content', 'selling content dm',
      'snapchat nudes', 'premium snap dm', 'e-girl dm', 'link in bio nudes', 'free nudes',
      'sex dating', 'meet singles near you', 'dm me for pics',
    ],
  },
];
