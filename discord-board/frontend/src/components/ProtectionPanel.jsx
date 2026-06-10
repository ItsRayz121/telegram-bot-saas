import { useEffect, useState } from "react";
import { api } from "../api";

const TEXT_TYPES = new Set([0, 5]);
const CF_ACTIONS = ["delete", "warn", "timeout", "kick", "ban"];
const RG_ACTIONS = ["timeout", "kick"];

const CATEGORY_LABEL = {
  nsfw: "NSFW", csam: "CSAM", invite: "Invite", link: "Link", custom: "Blocked word",
  spam: "Spam", raid: "Raid", lockdown_join: "Lockdown join", join_gate: "Join gate",
  manual_lockdown: "Lockdown",
};

export default function ProtectionPanel({ guildId, channels }) {
  const [cfg, setCfg] = useState(null);
  const [wordsText, setWordsText] = useState("");
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  const textChannels = (channels || []).filter((c) => TEXT_TYPES.has(c.type));

  async function loadEvents() {
    try {
      const d = await api(`/api/guilds/${guildId}/protection/events?limit=50`);
      setEvents(d.events);
    } catch {
      /* non-fatal */
    }
  }

  useEffect(() => {
    api(`/api/guilds/${guildId}/moderation`)
      .then((d) => {
        setCfg(d);
        setWordsText((d.cf_custom_words || []).join(", "));
      })
      .catch(() => setError("Failed to load protection settings."))
      .finally(() => setLoading(false));
    loadEvents(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId]);

  function set(patch) {
    setCfg((c) => ({ ...c, ...patch }));
    setSaved(false);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const payload = {
        ...cfg,
        cf_custom_words: wordsText.split(",").map((w) => w.trim()).filter(Boolean),
      };
      const d = await api(`/api/guilds/${guildId}/moderation`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      setCfg(d);
      setWordsText((d.cf_custom_words || []).join(", "));
      setSaved(true);
    } catch {
      setError("Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function lockdown(minutes) {
    const d = await api(`/api/guilds/${guildId}/moderation/lockdown`, {
      method: "POST",
      body: JSON.stringify({ minutes }),
    });
    setCfg(d);
    loadEvents();
  }

  if (loading) return <p className="muted">Loading…</p>;
  if (!cfg) return <div className="alert">{error || "No settings."}</div>;

  return (
    <>
      <div className="detail-grid">
        <section className="panel">
          <h2>Content filter</h2>
          <label className="check">
            <input type="checkbox" checked={cfg.cf_enabled} onChange={(e) => set({ cf_enabled: e.target.checked })} />
            Scan messages and act on violations
          </label>
          <label className="field">
            <span>Action on violation</span>
            <select value={cfg.cf_action} onChange={(e) => set({ cf_action: e.target.value })}>
              {CF_ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
            <small className="muted">CSAM always bans regardless of this setting.</small>
          </label>
          <label className="check">
            <input type="checkbox" checked={cfg.cf_nsfw} onChange={(e) => set({ cf_nsfw: e.target.checked })} />
            Block NSFW / explicit content
          </label>
          <label className="check">
            <input type="checkbox" checked={cfg.cf_invites} onChange={(e) => set({ cf_invites: e.target.checked })} />
            Remove foreign Discord invites
          </label>
          <label className="check">
            <input type="checkbox" checked={cfg.cf_links} onChange={(e) => set({ cf_links: e.target.checked })} />
            Remove shortened / suspicious links
          </label>
          <label className="field">
            <span>Custom blocked words</span>
            <input value={wordsText} placeholder="word1, word2, …" onChange={(e) => { setWordsText(e.target.value); setSaved(false); }} />
            <small className="muted">Comma-separated. Matched leniently (leet/spacing aware).</small>
          </label>
        </section>

        <section className="panel">
          <h2>Raid guard</h2>
          <label className="check">
            <input type="checkbox" checked={cfg.rg_enabled} onChange={(e) => set({ rg_enabled: e.target.checked })} />
            Auto-lock on coordinated spam
          </label>
          <p className="muted small">Triggers on many distinct accounts tripping the filter, or posting identical text, within the window — not raw join rate.</p>
          <NumField label="Window (seconds)" value={cfg.rg_window_seconds} min={10} max={600} onChange={(v) => set({ rg_window_seconds: v })} />
          <NumField label="Violators to trigger" value={cfg.rg_trigger_violators} min={2} max={50} onChange={(v) => set({ rg_trigger_violators: v })} />
          <NumField label="Duplicate-flood threshold" value={cfg.rg_duplicate_threshold} min={2} max={50} onChange={(v) => set({ rg_duplicate_threshold: v })} />
          <NumField label="Lockdown minutes" value={cfg.rg_lockdown_minutes} min={1} max={1440} onChange={(v) => set({ rg_lockdown_minutes: v })} />
          <label className="field">
            <span>Lockdown action for joiners</span>
            <select value={cfg.rg_lockdown_action} onChange={(e) => set({ rg_lockdown_action: e.target.value })}>
              {RG_ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
          <label className="check">
            <input type="checkbox" checked={cfg.rg_notify} onChange={(e) => set({ rg_notify: e.target.checked })} />
            Announce when raid mode activates
          </label>
          <label className="field">
            <span>Announce in channel</span>
            <select value={cfg.rg_notify_channel_id || ""} onChange={(e) => set({ rg_notify_channel_id: e.target.value || null })}>
              <option value="">— system channel —</option>
              {textChannels.map((c) => <option key={c.id} value={c.id}># {c.name}</option>)}
            </select>
          </label>
        </section>

        <section className="panel">
          <h2>Join gate</h2>
          <NumField
            label="Minimum account age (days, 0 = off)"
            value={cfg.jg_min_account_age_days} min={0} max={365}
            onChange={(v) => set({ jg_min_account_age_days: v })}
          />
          <small className="muted">Newer accounts are kicked on join. Useful during raids.</small>
        </section>

        <section className="panel">
          <h2>Emergency lockdown</h2>
          {cfg.manual_lockdown_active ? (
            <>
              <p className="lockdown-on">🔒 Lockdown active until {new Date(cfg.manual_lockdown_until).toLocaleString()}</p>
              <button className="btn-secondary" onClick={() => lockdown(0)}>Lift lockdown</button>
            </>
          ) : (
            <>
              <p className="muted small">Instantly restrict every new joiner (timeout/kick per raid-guard action).</p>
              <div className="form-actions">
                <button className="btn-primary" onClick={() => lockdown(30)}>Lock 30 min</button>
                <button className="btn-secondary" onClick={() => lockdown(120)}>Lock 2 h</button>
              </div>
            </>
          )}
        </section>

        <div className="save-bar">
          {error && <span className="alert inline">{error}</span>}
          {saved && <span className="saved-note">Saved ✓</span>}
          <button className="btn-primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>

      <section className="panel" style={{ marginTop: 20 }}>
        <h2>Protection activity</h2>
        {events.length === 0 && <p className="muted">No events yet.</p>}
        <ul className="feed">
          {events.map((e) => (
            <li key={e.id} className="feed-row">
              <span className={`tag tag-${e.category}`}>{CATEGORY_LABEL[e.category] || e.category}</span>
              <span className="feed-action">{e.action}</span>
              <span className="feed-detail">{e.username ? `${e.username} — ` : ""}{e.detail}</span>
              <span className="feed-time">{new Date(e.created_at).toLocaleString()}</span>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}

function NumField({ label, value, min, max, onChange }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        type="number" value={value} min={min} max={max}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}
