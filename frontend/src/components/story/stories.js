// Story scripts for the landing-page heroes. One engine (StoryHero.jsx), three products.
//
// Every product tells the same arc so the three pages feel like one family:
//   1. calm  — everything is fine, the person steps away
//   2. alarm — what happens without us
//   3. safe  — the same moment, with us
//   4–6      — what else keeps running while nobody is watching, then the recap
//
// Event types (t = ms from the start of the chapter):
//   msg      { id, name, text }                 a member's message
//   me       { text }                           the reader's own message (Echo DMs)
//   bot      { text, tag? }                     the product's bot, under the story's bot name
//   media    { id, name, label }                an explicit image, shown blurred
//   fwd      { id, name, from, text }           a forwarded message
//   service  { text, tone? }                    a system line; tone 'red' | 'green'
//   remove   { target, reason }                 strikes out an earlier message
//   members  { delta }                          changes the header member count
//   card     { card, ...props }                 a rich card (verify, campaign, cost, summary…)
//
// All names, numbers and messages are illustrative. Only show features the product has.

export const TELEGIZER_STORY = {
  skin: 'telegram',
  label: 'Story: what happens to a Telegram group while its admin is away',
  botName: 'Base Guard',
  header: { title: 'Base builders', avatar: 'B' },
  members: 12847,
  scenes: [
    {
      key: 'calm', time: '18:00', tone: 'calm', dur: 4200,
      title: 'Your admin steps away',
      body: 'Five minutes for dinner. The group is quiet.',
      status: { text: 'admin online', tone: 'green' },
      events: [
        { t: 0, type: 'msg', id: 'a', name: 'nik.eth', text: 'anyone know when the snapshot is?' },
        { t: 0, type: 'msg', id: 'b', name: 'sara · admin', text: 'grabbing food, back in 5 min' },
        { t: 0, type: 'service', text: 'sara is offline' },
      ],
    },
    {
      key: 'flood', time: '18:01', tone: 'alarm', dur: 7600,
      title: 'Without Telegizer',
      body: 'Bots pour in with scam links, explicit images and fake support. Real members start leaving.',
      status: { text: 'no admin online', tone: 'red' },
      events: [
        { t: 200, type: 'service', text: '37 accounts joined in 20 seconds', tone: 'red' },
        { t: 900, type: 'msg', id: 's1', name: 'claim_drop', text: 'Claim 5,000 $BASE free, today only: t.me/+x9Kq…' },
        { t: 1600, type: 'media', id: 's2', name: 'hot_dm_24', label: 'Photo' },
        { t: 2300, type: 'fwd', id: 's3', name: 'wallet_help', from: 'Wallet Support', text: 'Your wallet is flagged. Verify here to unlock it.' },
        { t: 3000, type: 'msg', id: 's4', name: 'claim_drop2', text: 'Claim 5,000 $BASE free, today only: t.me/+x9Kq…' },
        { t: 3700, type: 'msg', id: 'r1', name: 'mira_k', text: 'what is going on, where are the admins??' },
        { t: 4400, type: 'msg', id: 'r2', name: 'dan_ol', text: 'third time this week. I’m out' },
        { t: 4800, type: 'service', text: 'dan_ol left the group' },
        { t: 4800, type: 'members', delta: -57 },
        { t: 5600, type: 'card', card: 'cost', rows: [['214', 'spam messages'], ['57', 'members left'], ['3', 'clicked the fake wallet link']] },
      ],
    },
    {
      key: 'shield', time: '18:01', tone: 'safe', dur: 7200,
      title: 'The same five minutes, with Telegizer',
      body: 'Raid mode holds the bot wave. Links, explicit media and forwarded scams are deleted before anyone reads them.',
      status: { text: 'Telegizer on duty', tone: 'green' },
      events: [
        { t: 200, type: 'service', text: 'raid mode on · 37 new accounts held for verification', tone: 'green' },
        { t: 1000, type: 'msg', id: 'x1', name: 'claim_drop', text: 'Claim 5,000 $BASE free, today only: t.me/+x9Kq…' },
        { t: 1500, type: 'remove', target: 'x1', reason: 'link spam · banned' },
        { t: 2300, type: 'media', id: 'x2', name: 'hot_dm_24', label: 'Photo' },
        { t: 2700, type: 'remove', target: 'x2', reason: 'explicit media · banned' },
        { t: 3500, type: 'fwd', id: 'x3', name: 'wallet_help', from: 'Wallet Support', text: 'Your wallet is flagged. Verify here to unlock it.' },
        { t: 3900, type: 'remove', target: 'x3', reason: 'forwarded scam · muted 24h' },
        { t: 4900, type: 'msg', id: 'x4', name: 'mira_k', text: 'that was fast. nice' },
      ],
    },
    {
      key: 'welcome', time: '18:02', tone: 'safe', dur: 6600,
      title: 'Your bot, under your name',
      body: 'Real people pass a one-tap check and get a welcome. Custom bots carry your project’s name and picture.',
      status: { text: 'Telegizer on duty', tone: 'green' },
      events: [
        { t: 200, type: 'service', text: 'lena joined via invite link “twitter-bio”' },
        { t: 900, type: 'card', card: 'verify', who: 'Lena' },
        { t: 2400, type: 'service', text: 'lena verified in 4 s', tone: 'green' },
        { t: 3000, type: 'bot', text: 'Welcome, Lena. The rules are pinned. Say hi to earn your first 10 XP.', tag: 'your bot' },
        { t: 4300, type: 'msg', id: 'w1', name: 'lena', text: 'hey all, found you through the AMA' },
        { t: 4300, type: 'members', delta: 1 },
      ],
    },
    {
      key: 'engage', time: '18:03', tone: 'safe', dur: 7600,
      title: 'The group keeps working',
      body: 'AI answers from your own docs. Campaigns check each task, collect wallets and pay out XP by themselves.',
      status: { text: 'Telegizer on duty', tone: 'green' },
      events: [
        { t: 200, type: 'msg', id: 'e1', name: 'nik.eth', text: 'anyone know when the snapshot is?' },
        { t: 1000, type: 'bot', text: 'Snapshot is Dec 2 at 14:00 UTC. The full steps are in the pinned FAQ.', tag: 'AI · from your docs' },
        { t: 2300, type: 'card', card: 'campaign', title: 'Repost the launch on X', reward: '+50 XP', done: 38, total: 100, ends: 'ends in 2 days' },
        { t: 3900, type: 'service', text: 'mira_k: proof checked · wallet saved · +50 XP', tone: 'green' },
        { t: 4700, type: 'service', text: 'dan_ol reached level 5 · Regular role' },
        { t: 5400, type: 'card', card: 'leaderboard', rows: [['mira_k', 1240], ['dan_ol', 980], ['nik.eth', 905]] },
      ],
    },
    {
      key: 'recap', time: '18:05', tone: 'safe', dur: 6800,
      title: 'You come back to a better group',
      body: 'One dashboard shows what happened. Every action sits in the audit log, shared with your other admins.',
      status: { text: 'admin online', tone: 'green' },
      events: [
        { t: 200, type: 'msg', id: 'z1', name: 'sara · admin', text: 'back. did I miss anything?' },
        {
          t: 900, type: 'card', card: 'summary', title: 'While you were away',
          rows: [['214', 'spam removed'], ['37', 'bot joins held'], ['4', 'members welcomed'], ['12', 'tasks verified'], ['9', 'questions answered'], ['0', 'members lost']],
          foot: 'saved to the audit log · visible to 3 admins',
        },
      ],
    },
  ],
};

export const GUILDIZER_STORY = {
  skin: 'discord',
  label: 'Story: what happens to a Discord server while its moderators are away',
  botName: 'Base Guard',
  header: { title: 'general', server: 'Base builders' },
  members: 8540,
  scenes: [
    {
      key: 'calm', time: '18:00', tone: 'calm', dur: 4200,
      title: 'Your mods step away',
      body: 'Five minutes for dinner. #general is quiet.',
      status: { text: '2 mods online', tone: 'green' },
      events: [
        { t: 0, type: 'msg', id: 'a', name: 'nik', text: 'anyone know when the snapshot is?' },
        { t: 0, type: 'msg', id: 'b', name: 'sara', role: 'Mod', text: 'grabbing food, back in 5' },
        { t: 0, type: 'service', text: 'sara is now idle' },
      ],
    },
    {
      key: 'flood', time: '18:01', tone: 'alarm', dur: 7600,
      title: 'Without Guildizer',
      body: 'A raid hits. Fake Nitro, explicit images and phishing DMs land faster than anyone can react.',
      status: { text: 'no mods online', tone: 'red' },
      events: [
        { t: 200, type: 'service', text: '41 new members joined in 20 seconds', tone: 'red' },
        { t: 900, type: 'msg', id: 's1', name: 'nitro_drop', text: '@everyone free Nitro for 3 months → discord-gift.co/x9Kq' },
        { t: 1600, type: 'media', id: 's2', name: 'hot_dm_24', label: 'image.png' },
        { t: 2300, type: 'msg', id: 's3', name: 'steam_support', text: 'Your account is reported. Verify it here or it gets banned.' },
        { t: 3000, type: 'msg', id: 's4', name: 'nitro_drop2', text: '@everyone free Nitro for 3 months → discord-gift.co/x9Kq' },
        { t: 3700, type: 'msg', id: 'r1', name: 'mira', text: 'mods?? this is the third raid' },
        { t: 4400, type: 'msg', id: 'r2', name: 'dan', text: 'muting this server, I’m done' },
        { t: 4800, type: 'service', text: 'dan left the server' },
        { t: 4800, type: 'members', delta: -63 },
        { t: 5600, type: 'card', card: 'cost', rows: [['260', 'spam messages'], ['63', 'members left'], ['5', 'opened the phishing link']] },
      ],
    },
    {
      key: 'shield', time: '18:01', tone: 'safe', dur: 7200,
      title: 'The same five minutes, with Guildizer',
      body: 'Anti-raid pauses joins. AutoMod deletes the links, the images and the fake support before anyone clicks.',
      status: { text: 'Guildizer on duty', tone: 'green' },
      events: [
        { t: 200, type: 'service', text: 'raid detected · joins paused · 41 accounts quarantined', tone: 'green' },
        { t: 1000, type: 'msg', id: 'x1', name: 'nitro_drop', text: '@everyone free Nitro for 3 months → discord-gift.co/x9Kq' },
        { t: 1500, type: 'remove', target: 'x1', reason: 'scam link · banned' },
        { t: 2300, type: 'media', id: 'x2', name: 'hot_dm_24', label: 'image.png' },
        { t: 2700, type: 'remove', target: 'x2', reason: 'explicit media · banned' },
        { t: 3500, type: 'msg', id: 'x3', name: 'steam_support', text: 'Your account is reported. Verify it here or it gets banned.' },
        { t: 3900, type: 'remove', target: 'x3', reason: 'phishing · timed out 24h' },
        { t: 4900, type: 'msg', id: 'x4', name: 'mira', text: 'wait, it’s already gone? nice' },
      ],
    },
    {
      key: 'welcome', time: '18:02', tone: 'safe', dur: 6600,
      title: 'Your bot, under your name',
      body: 'New members verify, pick their roles and get a welcome from a bot that carries your server’s name.',
      status: { text: 'Guildizer on duty', tone: 'green' },
      events: [
        { t: 200, type: 'service', text: 'lena joined from invite “twitter-bio”' },
        { t: 900, type: 'card', card: 'verify', who: 'Lena', roles: true },
        { t: 2400, type: 'service', text: 'lena got Verified and Builder', tone: 'green' },
        { t: 3000, type: 'bot', text: 'Welcome, Lena. Rules are in #start-here. Say hi to earn your first XP.', tag: 'your bot' },
        { t: 4300, type: 'msg', id: 'w1', name: 'lena', text: 'hey all, found you through the AMA' },
        { t: 4300, type: 'members', delta: 1 },
      ],
    },
    {
      key: 'engage', time: '18:03', tone: 'safe', dur: 7600,
      title: 'The server keeps working',
      body: 'AI answers from your docs. Campaigns check each task and hand out XP and roles by themselves.',
      status: { text: 'Guildizer on duty', tone: 'green' },
      events: [
        { t: 200, type: 'msg', id: 'e1', name: 'nik', text: 'anyone know when the snapshot is?' },
        { t: 1000, type: 'bot', text: 'Snapshot is Dec 2 at 14:00 UTC. Full steps are in #faq.', tag: 'AI · from your docs' },
        { t: 2300, type: 'card', card: 'campaign', title: 'Repost the launch on X', reward: '+50 XP · OG role', done: 38, total: 100, ends: 'ends in 2 days' },
        { t: 3900, type: 'service', text: 'mira: proof checked · wallet saved · +50 XP', tone: 'green' },
        { t: 4700, type: 'service', text: 'dan reached level 5 · got Regular' },
        { t: 5400, type: 'card', card: 'leaderboard', rows: [['mira', 1240], ['dan', 980], ['nik', 905]] },
      ],
    },
    {
      key: 'recap', time: '18:05', tone: 'safe', dur: 6800,
      title: 'You come back to a better server',
      body: 'One dashboard shows what happened. Every action sits in the mod log, shared with your whole team.',
      status: { text: '2 mods online', tone: 'green' },
      events: [
        { t: 200, type: 'msg', id: 'z1', name: 'sara', role: 'Mod', text: 'back. did I miss anything?' },
        {
          t: 900, type: 'card', card: 'summary', title: 'While you were away',
          rows: [['260', 'spam removed'], ['41', 'raid accounts held'], ['4', 'members welcomed'], ['12', 'tasks verified'], ['9', 'questions answered'], ['0', 'members lost']],
          foot: 'saved to the mod log · visible to 4 mods',
        },
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
      key: 'calm', time: '09:00', tone: 'calm', dur: 4200,
      title: 'A busy Monday starts',
      body: 'Three meetings, two chats, one inbox. Something will get dropped.',
      status: { text: 'online', tone: 'green' },
      events: [
        { t: 0, type: 'service', text: 'Monday · 9 unread chats' },
        { t: 0, type: 'fwd', id: 'a', name: 'you', from: 'Sam (Design)', text: 'can you send the deck before Thursday?' },
      ],
    },
    {
      key: 'flood', time: '11:40', tone: 'alarm', dur: 7000,
      title: 'Without Echo',
      body: 'Promises get buried under new messages. The deck is still unsent on Thursday.',
      status: { text: 'no reminders set', tone: 'red' },
      events: [
        { t: 200, type: 'fwd', id: 's1', name: 'you', from: 'Ops team', text: 'invoice due Friday, please approve' },
        { t: 1000, type: 'fwd', id: 's2', name: 'you', from: 'Priya', text: 'link to the pricing doc we discussed?' },
        { t: 1800, type: 'fwd', id: 's3', name: 'you', from: 'Investor group', text: 'call moved to 4pm' },
        { t: 2600, type: 'service', text: '43 new messages since your last check', tone: 'red' },
        { t: 3400, type: 'fwd', id: 's4', name: 'you', from: 'Sam (Design)', text: 'hey, still waiting on that deck…' },
        { t: 4400, type: 'card', card: 'cost', title: 'By Thursday', rows: [['1', 'deck never sent'], ['1', 'invoice paid late'], ['1', 'call missed at 4pm']] },
      ],
    },
    {
      key: 'shield', time: '11:40', tone: 'safe', dur: 7000,
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
      key: 'welcome', time: '14:10', tone: 'safe', dur: 6200,
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
      key: 'engage', time: '15:45', tone: 'safe', dur: 5800,
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
      key: 'recap', time: '08:00', tone: 'safe', dur: 6800,
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
