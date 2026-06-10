import { useEffect, useState } from "react";
import { api } from "../api";

// Text-postable channel types (text, announcement).
const TEXT_TYPES = new Set([0, 5]);

export default function SettingsPanel({ guildId, channels, roles }) {
  const [cfg, setCfg] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  const textChannels = (channels || []).filter((c) => TEXT_TYPES.has(c.type));
  const assignableRoles = (roles || []).filter((r) => r.name !== "@everyone" && !r.managed);

  useEffect(() => {
    api(`/api/guilds/${guildId}/settings`)
      .then((d) => setCfg(d))
      .catch(() => setError("Failed to load settings."))
      .finally(() => setLoading(false));
  }, [guildId]);

  function set(patch) {
    setCfg((c) => ({ ...c, ...patch }));
    setSaved(false);
  }
  function toggleRole(id) {
    const has = cfg.autorole_ids.includes(id);
    set({ autorole_ids: has ? cfg.autorole_ids.filter((r) => r !== id) : [...cfg.autorole_ids, id] });
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const d = await api(`/api/guilds/${guildId}/settings`, {
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
        <h2>Welcome message</h2>
        <label className="check">
          <input
            type="checkbox"
            checked={cfg.welcome_enabled}
            onChange={(e) => set({ welcome_enabled: e.target.checked })}
          />
          Send a message when a member joins
        </label>
        <ChannelSelect
          label="Channel"
          value={cfg.welcome_channel_id}
          channels={textChannels}
          onChange={(v) => set({ welcome_channel_id: v })}
        />
        <label className="field">
          <span>Message</span>
          <textarea
            rows={3}
            value={cfg.welcome_message}
            maxLength={2000}
            onChange={(e) => set({ welcome_message: e.target.value })}
          />
          <small className="muted">Placeholders: {"{user}"} {"{server}"} {"{member_count}"}</small>
        </label>
      </section>

      <section className="panel">
        <h2>Leave message</h2>
        <label className="check">
          <input
            type="checkbox"
            checked={cfg.leave_enabled}
            onChange={(e) => set({ leave_enabled: e.target.checked })}
          />
          Send a message when a member leaves
        </label>
        <ChannelSelect
          label="Channel"
          value={cfg.leave_channel_id}
          channels={textChannels}
          onChange={(v) => set({ leave_channel_id: v })}
        />
        <label className="field">
          <span>Message</span>
          <textarea
            rows={3}
            value={cfg.leave_message}
            maxLength={2000}
            onChange={(e) => set({ leave_message: e.target.value })}
          />
        </label>
      </section>

      <section className="panel">
        <h2>Auto-roles</h2>
        <label className="check">
          <input
            type="checkbox"
            checked={cfg.autorole_enabled}
            onChange={(e) => set({ autorole_enabled: e.target.checked })}
          />
          Assign roles automatically on join
        </label>
        {assignableRoles.length === 0 && <p className="muted small">No assignable roles.</p>}
        <div className="chips">
          {assignableRoles.map((r) => {
            const on = cfg.autorole_ids.includes(r.id);
            return (
              <button
                key={r.id}
                className={`chip ${on ? "on" : ""}`}
                onClick={() => toggleRole(r.id)}
                type="button"
              >
                <span className="role-dot" style={{ background: r.color || "#99aab5" }} />
                {r.name}
              </button>
            );
          })}
        </div>
        <small className="muted">Guildizer's role must sit above any role it assigns.</small>
      </section>

      <div className="save-bar">
        {error && <span className="alert inline">{error}</span>}
        {saved && <span className="saved-note">Saved ✓</span>}
        <button className="btn-primary" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save changes"}
        </button>
      </div>
    </div>
  );
}

function ChannelSelect({ label, value, channels, onChange }) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value || ""} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">— none —</option>
        {channels.map((c) => (
          <option key={c.id} value={c.id}>
            # {c.name}
          </option>
        ))}
      </select>
    </label>
  );
}
