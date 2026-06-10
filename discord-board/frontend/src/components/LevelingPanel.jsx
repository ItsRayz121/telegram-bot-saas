import { useEffect, useState } from "react";
import { api } from "../api";

const TEXT_TYPES = new Set([0, 5]);

export default function LevelingPanel({ guildId, channels }) {
  const [cfg, setCfg] = useState(null);
  const [board, setBoard] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  const textChannels = (channels || []).filter((c) => TEXT_TYPES.has(c.type));

  useEffect(() => {
    Promise.all([
      api(`/api/guilds/${guildId}/leveling`),
      api(`/api/guilds/${guildId}/leaderboard?limit=10`).catch(() => ({ leaderboard: [] })),
    ])
      .then(([s, b]) => {
        setCfg(s);
        setBoard(b.leaderboard || []);
      })
      .catch(() => setError("Failed to load leveling."))
      .finally(() => setLoading(false));
  }, [guildId]);

  function set(patch) {
    setCfg((c) => ({ ...c, ...patch }));
    setSaved(false);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const d = await api(`/api/guilds/${guildId}/leveling`, {
        method: "PUT",
        body: JSON.stringify(cfg),
      });
      setCfg(d);
      setSaved(true);
    } catch {
      setError("Save failed.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <p className="muted">Loading…</p>;
  if (!cfg) return <div className="alert">{error || "No settings."}</div>;

  return (
    <div className="detail-grid">
      <section className="panel">
        <h2>XP &amp; levels</h2>
        <label className="check">
          <input type="checkbox" checked={cfg.levels_enabled} onChange={(e) => set({ levels_enabled: e.target.checked })} />
          Award XP for chatting (100 XP per level)
        </label>
        <label className="field">
          <span>XP per message</span>
          <input type="number" min={0} max={1000} value={cfg.xp_per_message}
            onChange={(e) => set({ xp_per_message: Number(e.target.value) })} />
        </label>
        <label className="field">
          <span>Cooldown between awards (seconds)</span>
          <input type="number" min={0} max={3600} value={cfg.xp_cooldown_seconds}
            onChange={(e) => set({ xp_cooldown_seconds: Number(e.target.value) })} />
        </label>
        <label className="check">
          <input type="checkbox" checked={cfg.announce_level_up} onChange={(e) => set({ announce_level_up: e.target.checked })} />
          Announce level-ups
        </label>
        <label className="field">
          <span>Announce in channel</span>
          <select value={cfg.levelup_channel_id || ""} onChange={(e) => set({ levelup_channel_id: e.target.value || null })}>
            <option value="">— same channel as message —</option>
            {textChannels.map((c) => <option key={c.id} value={c.id}># {c.name}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Level-up message</span>
          <input value={cfg.levelup_message} maxLength={1000} placeholder="🎉 {user} reached level {level}!"
            onChange={(e) => set({ levelup_message: e.target.value })} />
          <small className="muted">Placeholders: {"{user}"} {"{username}"} {"{level}"}</small>
        </label>
        <div className="form-actions">
          {error && <span className="alert inline">{error}</span>}
          {saved && <span className="saved-note">Saved ✓</span>}
          <button className="btn-primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </section>

      <section className="panel">
        <h2>Leaderboard</h2>
        {board.length === 0 && <p className="muted">No XP earned yet.</p>}
        <ul className="list">
          {board.map((m) => (
            <li key={m.user_id} className="list-row">
              <span className="rank-badge">#{m.rank}</span>
              <span className="list-name">{m.username || m.user_id}</span>
              <span className="badge">Lvl {m.level}</span>
              <span className="muted small">{m.xp} XP</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
