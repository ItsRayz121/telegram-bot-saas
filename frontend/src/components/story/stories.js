// Story scripts for the landing-page heroes. One engine (StoryHero.jsx), three products.
//
// Telegizer and Guildizer tell the same arc, chapter for chapter:
//   1. calm     the admin leaves for dinner
//   2. flood    five minutes without a moderator          (act: without)
//   3. back     the admin returns to the damage           (act: without)
//   4. shield   the same five minutes, with us            (act: with)
//   5. answers  real people verified, welcomed, answered  (act: with)
//   6. rewards  tasks checked and paid out automatically  (act: with)
//   7. ownbot   your own bot in under a minute            (act: with, the only white-label chapter)
//   8. recap    the admin returns to a better group       (act: with)
// Member-count changes carry forward only within the same act.
//
// Event types (t = ms from the start of the chapter):
//   msg      { id, name, text, role? }        a member's message
//   me       { text }                         the reader's own message (Echo DMs)
//   bot      { text, tag?, own? }             the product's bot; own: true shows the custom bot instead
//   media    { id, name, label }              an explicit image, shown blurred
//   fwd      { id, name, from, text }         a forwarded message
//   sticker  { name, art, role? }             a sticker someone sent (art from Stickers.jsx)
//   stamp    { art, text, dur }               a big overlay over the chat for a dramatic beat
//   service  { text, tone? }                  a system line; tone 'red' | 'green'
//   remove   { target, reason }               strikes out an earlier message
//   members  { delta }                        changes the header member count
//   card     { card, ...props }               cost, verify, campaign, proof, leaderboard, setup, summary
//
// All names, numbers and messages are illustrative. Only show features the product has.

const SPAM_LINK = 'Claim 5,000 $BASE free, today only: t.me/+x9Kq…';
const NUDE_LINK = 'hot pics in my bio 🔞 t.me/+hx7…';
const FAKE_SUPPORT = 'Your wallet is flagged. Verify here to unlock it.';

export const TELEGIZER_STORY = {
  skin: 'telegram',
  label: 'Story: what happens to a Telegram group while its admin is away',
  botName: 'Telegizer',
  ownBot: { name: 'Base Guard', avatar: 'BG' },
  header: { title: 'Base builders', avatar: 'B' },
  members: 12847,
  scenes: [
    {
      key: 'calm', time: '18:00', tone: 'calm', dur: 4600,
      title: 'Your admin steps away',
      body: 'Five minutes for dinner. The group is quiet.',
      status: { text: 'admin online', tone: 'green' },
      events: [
        { t: 0, type: 'msg', id: 'a', name: 'nik.eth', text: 'anyone know when the snapshot is?' },
        { t: 0, type: 'msg', id: 'b', name: 'sara', role: 'admin', text: 'grabbing dinner, back in 5' },
        { t: 0, type: 'sticker', name: 'sara', role: 'admin', art: 'dinner' },
        { t: 0, type: 'service', text: 'sara is offline' },
      ],
    },
    {
      key: 'flood', act: 'without', time: '18:01', tone: 'alarm', dur: 8800,
      title: 'Five minutes without a moderator',
      body: 'Bots pour in with scam links, nude links and fake support. Real members panic and start leaving.',
      status: { text: 'no admin online', tone: 'red' },
      events: [
        { t: 100, type: 'stamp', art: 'alert', text: 'Bot raid', dur: 1500 },
        { t: 400, type: 'service', text: '37 accounts joined in 20 seconds', tone: 'red' },
        { t: 1600, type: 'msg', id: 's1', name: 'claim_drop', text: SPAM_LINK },
        { t: 2200, type: 'msg', id: 's2', name: 'lina_xo', text: NUDE_LINK },
        { t: 2800, type: 'media', id: 's3', name: 'lina_xo', label: 'Photo' },
        { t: 3400, type: 'fwd', id: 's4', name: 'wallet_help', from: 'Wallet Support', text: FAKE_SUPPORT },
        { t: 4000, type: 'msg', id: 's5', name: 'claim_drop2', text: SPAM_LINK },
        { t: 4700, type: 'msg', id: 'r1', name: 'mira_k', text: 'why are these links here?? where are the admins' },
        { t: 5200, type: 'sticker', name: 'mira_k', art: 'worried' },
        { t: 6000, type: 'msg', id: 'r2', name: 'dan_ol', text: 'someone just got drained. I’m out' },
        { t: 6500, type: 'service', text: 'dan_ol and 56 others left the group' },
        { t: 6500, type: 'members', delta: -57 },
      ],
    },
    {
      key: 'back', act: 'without', time: '18:06', tone: 'alarm', dur: 5600,
      title: 'The admin comes back to a mess',
      body: 'Too late to clean up. The members who left are not coming back.',
      status: { text: 'admin online', tone: 'red' },
      events: [
        { t: 0, type: 'msg', id: 'k1', name: 'claim_drop', text: SPAM_LINK },
        { t: 0, type: 'msg', id: 'k2', name: 'lina_xo', text: NUDE_LINK },
        { t: 300, type: 'msg', id: 'k3', name: 'sara', role: 'admin', text: 'back. what happened here??' },
        { t: 900, type: 'stamp', art: 'late', text: 'Too late', dur: 1500 },
        { t: 2500, type: 'card', card: 'cost', title: 'Five minutes away cost you', rows: [['214', 'spam messages'], ['57', 'members left'], ['3', 'members scammed']] },
      ],
    },
    {
      key: 'shield', act: 'with', time: '18:01', tone: 'safe', dur: 8200,
      title: 'Now the same five minutes, with Telegizer',
      body: 'Raid mode holds the bots. Scam links, nude links, explicit media and fake forwards are gone in under a second.',
      status: { text: 'Telegizer on duty', tone: 'green' },
      events: [
        { t: 100, type: 'stamp', art: 'shield', text: 'Telegizer on duty', dur: 1400 },
        { t: 400, type: 'service', text: 'raid mode on · 37 new accounts held for verification', tone: 'green' },
        { t: 1600, type: 'msg', id: 'x1', name: 'claim_drop', text: SPAM_LINK },
        { t: 2000, type: 'remove', target: 'x1', reason: 'link spam · banned' },
        { t: 2600, type: 'msg', id: 'x2', name: 'lina_xo', text: NUDE_LINK },
        { t: 2950, type: 'remove', target: 'x2', reason: 'adult link · banned' },
        { t: 3500, type: 'media', id: 'x3', name: 'lina_xo', label: 'Photo' },
        { t: 3850, type: 'remove', target: 'x3', reason: 'explicit media · banned' },
        { t: 4400, type: 'fwd', id: 'x4', name: 'wallet_help', from: 'Wallet Support', text: FAKE_SUPPORT },
        { t: 4750, type: 'remove', target: 'x4', reason: 'forwarded scam · muted 24h' },
        { t: 5300, type: 'msg', id: 'x5', name: 'deal_bot', text: 'ch3ck my b.i.o for d-e-a-l-s' },
        { t: 5700, type: 'remove', target: 'x5', reason: 'hidden promo, caught by AI · warning 1/3' },
        { t: 6500, type: 'msg', id: 'x6', name: 'mira_k', text: 'that was fast. nice' },
      ],
    },
    {
      key: 'answers', act: 'with', time: '18:02', tone: 'safe', dur: 7600,
      title: 'Questions answered while you eat',
      body: 'Real people pass a one-tap check and get a welcome. The AI answers from your own docs.',
      status: { text: 'Telegizer on duty', tone: 'green' },
      events: [
        { t: 200, type: 'service', text: 'lena joined via invite link “twitter-bio”' },
        { t: 800, type: 'card', card: 'verify', who: 'Lena' },
        { t: 2100, type: 'service', text: 'lena verified in 4 s', tone: 'green' },
        { t: 2600, type: 'bot', text: 'Welcome, Lena. The rules are pinned. Say hi to earn your first 10 XP.', tag: 'welcome' },
        { t: 2600, type: 'members', delta: 1 },
        { t: 4000, type: 'msg', id: 'q1', name: 'nik.eth', text: 'anyone know when the snapshot is?' },
        { t: 4800, type: 'bot', text: 'Snapshot is Dec 2 at 14:00 UTC. The full steps are in the pinned FAQ.', tag: 'AI · from your docs' },
      ],
    },
    {
      key: 'rewards', act: 'with', time: '18:03', tone: 'safe', dur: 8400,
      title: 'Tasks checked, rewards paid',
      body: 'Members join campaigns and send proof. Telegizer checks it, saves their wallet and pays out XP.',
      status: { text: 'Telegizer on duty', tone: 'green' },
      events: [
        { t: 200, type: 'card', card: 'campaign', title: 'Repost the launch on X', reward: '+50 XP', done: 38, total: 100, ends: 'ends in 2 days' },
        { t: 1700, type: 'card', card: 'proof', who: 'mira_k', link: 'x.com/mira_k/status/18…', wallet: '0x7a3…91c' },
        { t: 3200, type: 'service', text: 'proof checked · wallet saved · mira_k +50 XP', tone: 'green' },
        { t: 3900, type: 'service', text: 'mira_k reached level 5 · Regular role' },
        { t: 4500, type: 'sticker', name: 'mira_k', art: 'trophy' },
        { t: 5500, type: 'card', card: 'leaderboard', rows: [['mira_k', 1290], ['dan_ol', 980], ['nik.eth', 905]] },
      ],
    },
    {
      key: 'ownbot', act: 'with', time: '18:04', tone: 'safe', dur: 7400,
      title: 'Your own bot, in under a minute',
      body: 'Paste a token from @BotFather and your group is run by a bot with your project’s name and picture. Pro and Enterprise.',
      status: { text: 'Base Guard on duty', tone: 'green' },
      events: [
        { t: 200, type: 'card', card: 'setup', steps: ['Paste the token from @BotFather', 'Pick a name and a picture', 'Live in your group'], time: '48 s' },
        { t: 2600, type: 'sticker', name: 'Base Guard', own: true, art: 'stopwatch' },
        { t: 3600, type: 'service', text: 'tom joined via invite link “partner-ama”' },
        { t: 4300, type: 'bot', own: true, text: 'Welcome to Base builders, Tom. I’m Base Guard. Rules are pinned.', tag: 'your bot' },
        { t: 4300, type: 'members', delta: 1 },
      ],
    },
    {
      key: 'recap', act: 'with', time: '18:06', tone: 'safe', dur: 7600,
      title: 'You come back to a better group',
      body: 'One dashboard shows what happened. Every action is in the audit log, shared with your other admins.',
      status: { text: 'admin online', tone: 'green' },
      events: [
        { t: 200, type: 'msg', id: 'z1', name: 'sara', role: 'admin', text: 'back. did I miss anything?' },
        {
          t: 900, type: 'card', card: 'summary', title: 'While you were away',
          rows: [['214', 'spam removed'], ['37', 'bot joins held'], ['9', 'questions answered'], ['12', 'tasks verified'], ['2', 'members welcomed'], ['0', 'members lost']],
          foot: 'saved to the audit log · visible to 3 admins',
        },
        { t: 3200, type: 'sticker', name: 'sara', role: 'admin', art: 'party' },
      ],
    },
  ],
};

const NITRO = '@everyone free Nitro for 3 months → discord-gift.co/x9Kq';
const D_NUDE = 'hot pics in my bio 🔞 discord.gg/hx7…';
const STEAM = 'Your account is reported. Verify it here or it gets banned.';

export const GUILDIZER_STORY = {
  skin: 'discord',
  label: 'Story: what happens to a Discord server while its moderators are away',
  botName: 'Guildizer',
  ownBot: { name: 'Base Guard', avatar: 'BG' },
  header: { title: 'general', server: 'Base builders' },
  members: 8540,
  scenes: [
    {
      key: 'calm', time: '18:00', tone: 'calm', dur: 4600,
      title: 'Your mods step away',
      body: 'Five minutes for dinner. #general is quiet.',
      status: { text: 'mods online', tone: 'green' },
      events: [
        { t: 0, type: 'msg', id: 'a', name: 'nik', text: 'anyone know when the snapshot is?' },
        { t: 0, type: 'msg', id: 'b', name: 'sara', role: 'Mod', text: 'grabbing dinner, back in 5' },
        { t: 0, type: 'sticker', name: 'sara', role: 'Mod', art: 'dinner' },
        { t: 0, type: 'service', text: 'sara is now idle' },
      ],
    },
    {
      key: 'flood', act: 'without', time: '18:01', tone: 'alarm', dur: 8800,
      title: 'Five minutes without a moderator',
      body: 'A raid hits. Fake Nitro, nude links and phishing land faster than anyone can react. Members leave.',
      status: { text: 'no mods online', tone: 'red' },
      events: [
        { t: 100, type: 'stamp', art: 'alert', text: 'Raid', dur: 1500 },
        { t: 400, type: 'service', text: '41 new members joined in 20 seconds', tone: 'red' },
        { t: 1600, type: 'msg', id: 's1', name: 'nitro_drop', text: NITRO },
        { t: 2200, type: 'msg', id: 's2', name: 'lina_xo', text: D_NUDE },
        { t: 2800, type: 'media', id: 's3', name: 'lina_xo', label: 'image.png' },
        { t: 3400, type: 'msg', id: 's4', name: 'steam_support', text: STEAM },
        { t: 4000, type: 'msg', id: 's5', name: 'nitro_drop2', text: NITRO },
        { t: 4700, type: 'msg', id: 'r1', name: 'mira', text: 'mods?? why are these links everywhere' },
        { t: 5200, type: 'sticker', name: 'mira', art: 'worried' },
        { t: 6000, type: 'msg', id: 'r2', name: 'dan', text: 'someone got phished. muting this server' },
        { t: 6500, type: 'service', text: 'dan and 62 others left the server' },
        { t: 6500, type: 'members', delta: -63 },
      ],
    },
    {
      key: 'back', act: 'without', time: '18:06', tone: 'alarm', dur: 5600,
      title: 'The mods come back to a mess',
      body: 'Too late to clean up. The members who left are not coming back.',
      status: { text: 'mods online', tone: 'red' },
      events: [
        { t: 0, type: 'msg', id: 'k1', name: 'nitro_drop', text: NITRO },
        { t: 0, type: 'msg', id: 'k2', name: 'lina_xo', text: D_NUDE },
        { t: 300, type: 'msg', id: 'k3', name: 'sara', role: 'Mod', text: 'back. what happened here??' },
        { t: 900, type: 'stamp', art: 'late', text: 'Too late', dur: 1500 },
        { t: 2500, type: 'card', card: 'cost', title: 'Five minutes away cost you', rows: [['260', 'spam messages'], ['63', 'members left'], ['5', 'members phished']] },
      ],
    },
    {
      key: 'shield', act: 'with', time: '18:01', tone: 'safe', dur: 8200,
      title: 'Now the same five minutes, with Guildizer',
      body: 'Anti-raid pauses joins. Scam links, nude links, explicit images and phishing are gone in under a second.',
      status: { text: 'Guildizer on duty', tone: 'green' },
      events: [
        { t: 100, type: 'stamp', art: 'shield', text: 'Guildizer on duty', dur: 1400 },
        { t: 400, type: 'service', text: 'raid detected · joins paused · 41 accounts quarantined', tone: 'green' },
        { t: 1600, type: 'msg', id: 'x1', name: 'nitro_drop', text: NITRO },
        { t: 2000, type: 'remove', target: 'x1', reason: 'scam link · banned' },
        { t: 2600, type: 'msg', id: 'x2', name: 'lina_xo', text: D_NUDE },
        { t: 2950, type: 'remove', target: 'x2', reason: 'adult link · banned' },
        { t: 3500, type: 'media', id: 'x3', name: 'lina_xo', label: 'image.png' },
        { t: 3850, type: 'remove', target: 'x3', reason: 'explicit media · banned' },
        { t: 4400, type: 'msg', id: 'x4', name: 'steam_support', text: STEAM },
        { t: 4750, type: 'remove', target: 'x4', reason: 'phishing · timed out 24h' },
        { t: 5300, type: 'msg', id: 'x5', name: 'deal_bot', text: 'ch3ck my b.i.o for d-e-a-l-s' },
        { t: 5700, type: 'remove', target: 'x5', reason: 'hidden promo · warning 1/3' },
        { t: 6500, type: 'msg', id: 'x6', name: 'mira', text: 'wait, it’s already gone? nice' },
      ],
    },
    {
      key: 'answers', act: 'with', time: '18:02', tone: 'safe', dur: 7600,
      title: 'Questions answered while you eat',
      body: 'New members verify and pick their roles. The AI answers from your own docs.',
      status: { text: 'Guildizer on duty', tone: 'green' },
      events: [
        { t: 200, type: 'service', text: 'lena joined from invite “twitter-bio”' },
        { t: 800, type: 'card', card: 'verify', who: 'Lena', roles: true },
        { t: 2100, type: 'service', text: 'lena got Verified and Builder', tone: 'green' },
        { t: 2600, type: 'bot', text: 'Welcome, Lena. Rules are in #start-here. Say hi to earn your first XP.', tag: 'welcome' },
        { t: 2600, type: 'members', delta: 1 },
        { t: 4000, type: 'msg', id: 'q1', name: 'nik', text: 'anyone know when the snapshot is?' },
        { t: 4800, type: 'bot', text: 'Snapshot is Dec 2 at 14:00 UTC. Full steps are in #faq.', tag: 'AI · from your docs' },
      ],
    },
    {
      key: 'rewards', act: 'with', time: '18:03', tone: 'safe', dur: 8400,
      title: 'Tasks checked, rewards paid',
      body: 'Members join campaigns and send proof. Guildizer checks it, saves their wallet and hands out XP and roles.',
      status: { text: 'Guildizer on duty', tone: 'green' },
      events: [
        { t: 200, type: 'card', card: 'campaign', title: 'Repost the launch on X', reward: '+50 XP · OG role', done: 38, total: 100, ends: 'ends in 2 days' },
        { t: 1700, type: 'card', card: 'proof', who: 'mira', link: 'x.com/mira/status/18…', wallet: '0x7a3…91c' },
        { t: 3200, type: 'service', text: 'proof checked · wallet saved · mira +50 XP · got OG', tone: 'green' },
        { t: 3900, type: 'service', text: 'mira reached level 5 · got Regular' },
        { t: 4500, type: 'sticker', name: 'mira', art: 'trophy' },
        { t: 5500, type: 'card', card: 'leaderboard', rows: [['mira', 1290], ['dan', 980], ['nik', 905]] },
      ],
    },
    {
      key: 'ownbot', act: 'with', time: '18:04', tone: 'safe', dur: 7400,
      title: 'Your own bot, in under a minute',
      body: 'Paste a bot token from the Discord developer portal and your server is run by a bot with your name and picture. Pro and Enterprise.',
      status: { text: 'Base Guard on duty', tone: 'green' },
      events: [
        { t: 200, type: 'card', card: 'setup', steps: ['Paste your bot token', 'Pick a name and a picture', 'Live in your server'], time: '52 s' },
        { t: 2600, type: 'sticker', name: 'Base Guard', own: true, art: 'stopwatch' },
        { t: 3600, type: 'service', text: 'tom joined from invite “partner-ama”' },
        { t: 4300, type: 'bot', own: true, text: 'Welcome to Base builders, Tom. I’m Base Guard. Grab your roles in #start-here.', tag: 'your bot' },
        { t: 4300, type: 'members', delta: 1 },
      ],
    },
    {
      key: 'recap', act: 'with', time: '18:06', tone: 'safe', dur: 7600,
      title: 'You come back to a better server',
      body: 'One dashboard shows what happened. Every action is in the mod log, shared with your whole team.',
      status: { text: 'mods online', tone: 'green' },
      events: [
        { t: 200, type: 'msg', id: 'z1', name: 'sara', role: 'Mod', text: 'back. did I miss anything?' },
        {
          t: 900, type: 'card', card: 'summary', title: 'While you were away',
          rows: [['260', 'spam removed'], ['41', 'raid accounts held'], ['9', 'questions answered'], ['12', 'tasks verified'], ['2', 'members welcomed'], ['0', 'members lost']],
          foot: 'saved to the mod log · visible to 4 mods',
        },
        { t: 3200, type: 'sticker', name: 'sara', role: 'Mod', art: 'party' },
      ],
    },
  ],
};

export const ECHO_STORY = {
  skin: 'echo',
  label: 'Story: how Echo keeps track of your day in Telegram',
  botName: 'Echo',
  header: { title: 'Echo', avatar: 'E' },
  scenes: [
    {
      key: 'calm', time: '09:00', tone: 'calm', dur: 4400,
      title: 'A busy Monday starts',
      body: 'Three meetings, two chats, one inbox. Something will get dropped.',
      status: { text: 'online', tone: 'green' },
      events: [
        { t: 0, type: 'service', text: 'Monday · 9 unread chats' },
        { t: 0, type: 'fwd', id: 'a', name: 'you', from: 'Sam (Design)', text: 'can you send the deck before Thursday?' },
      ],
    },
    {
      key: 'flood', act: 'without', time: '11:40', tone: 'alarm', dur: 7600,
      title: 'Without Echo',
      body: 'Promises get buried under new messages. The deck is still unsent on Thursday.',
      status: { text: 'no reminders set', tone: 'red' },
      events: [
        { t: 200, type: 'fwd', id: 's1', name: 'you', from: 'Ops team', text: 'invoice due Friday, please approve' },
        { t: 900, type: 'fwd', id: 's2', name: 'you', from: 'Priya', text: 'link to the pricing doc we discussed?' },
        { t: 1600, type: 'fwd', id: 's3', name: 'you', from: 'Investor group', text: 'call moved to 4pm' },
        { t: 2300, type: 'service', text: '43 new messages since your last check', tone: 'red' },
        { t: 3000, type: 'fwd', id: 's4', name: 'you', from: 'Sam (Design)', text: 'hey, still waiting on that deck…' },
        { t: 3500, type: 'stamp', art: 'late', text: 'Forgotten', dur: 1400 },
        { t: 5000, type: 'card', card: 'cost', title: 'By Thursday', rows: [['1', 'deck never sent'], ['1', 'invoice paid late'], ['1', 'call missed at 4pm']] },
      ],
    },
    {
      key: 'shield', act: 'with', time: '11:40', tone: 'safe', dur: 7200,
      title: 'The same morning, with Echo',
      body: 'Say it the way you would to a person. Echo turns it into a reminder, a task or a note.',
      status: { text: 'online', tone: 'green' },
      events: [
        { t: 200, type: 'me', text: 'remind me to send Sam the deck Wednesday at 10' },
        { t: 1100, type: 'bot', text: 'Done. Wednesday 10:00, “Send Sam the deck”.', tag: 'reminder set' },
        { t: 2300, type: 'me', text: 'task: approve the ops invoice by Friday' },
        { t: 3100, type: 'bot', text: 'Added to your tasks, due Friday.', tag: 'task' },
        { t: 4300, type: 'me', text: 'call with investors moved to 4pm' },
        { t: 5000, type: 'bot', text: 'Noted. I’ll nudge you at 15:45.', tag: 'reminder set' },
      ],
    },
    {
      key: 'links', act: 'with', time: '14:10', tone: 'safe', dur: 6400,
      title: 'Links and notes in one place',
      body: 'Save a link and Echo files it with a summary. Ask later and it finds it for you.',
      status: { text: 'online', tone: 'green' },
      events: [
        { t: 200, type: 'me', text: 'notion.so/pricing-v3' },
        { t: 1000, type: 'bot', text: 'Saved “Pricing v3”: three tiers, annual discount, draft for Priya.', tag: 'smart link' },
        { t: 2600, type: 'me', text: 'what was the pricing doc Priya asked about?' },
        { t: 3400, type: 'bot', text: 'That’s “Pricing v3”, saved today at 14:10. Want me to send it to her?', tag: 'AI · from your notes' },
      ],
    },
    {
      key: 'nudge', act: 'with', time: '15:45', tone: 'safe', dur: 6000,
      title: 'Nudged at the right moment',
      body: 'Reminders arrive in the chat you already have open, not in another app.',
      status: { text: 'online', tone: 'green' },
      events: [
        { t: 200, type: 'bot', text: 'Investor call in 15 minutes. Meeting link is ready.', tag: 'reminder' },
        { t: 1500, type: 'card', card: 'campaign', title: 'Investor call', reward: '16:00', done: 45, total: 60, ends: 'starts in 15 min', button: 'Open meeting link' },
        { t: 3200, type: 'me', text: 'thanks, joining' },
      ],
    },
    {
      key: 'recap', act: 'with', time: '08:00', tone: 'safe', dur: 7000,
      title: 'Every morning starts clear',
      body: 'An opt-in daily digest lists what is due, what is coming and what you saved.',
      status: { text: 'online', tone: 'green' },
      events: [
        {
          t: 300, type: 'card', card: 'summary', title: 'Your Wednesday',
          rows: [['10:00', 'send Sam the deck'], ['Fri', 'approve invoice'], ['3', 'tasks due'], ['2', 'links saved'], ['1', 'meeting today'], ['0', 'things forgotten']],
          foot: 'daily digest · sent at 08:00',
        },
      ],
    },
  ],
};
