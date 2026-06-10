import { useEffect, useState } from "react";
import { api } from "../api";

const BLANK = { name: "", description: "Custom command", response: "", enabled: true };

export default function CommandsPanel({ guildId }) {
  const [commands, setCommands] = useState([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState(BLANK);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const d = await api(`/api/guilds/${guildId}/commands`);
      setCommands(d.commands);
    } catch {
      setError("Failed to load commands.");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId]);

  function startEdit(cmd) {
    setEditingId(cmd.id);
    setDraft({ name: cmd.name, description: cmd.description, response: cmd.response, enabled: cmd.enabled });
    setError(null);
  }
  function cancel() {
    setEditingId(null);
    setDraft(BLANK);
    setError(null);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      if (editingId) {
        await api(`/api/guilds/${guildId}/commands/${editingId}`, {
          method: "PUT",
          body: JSON.stringify(draft),
        });
      } else {
        await api(`/api/guilds/${guildId}/commands`, {
          method: "POST",
          body: JSON.stringify(draft),
        });
      }
      cancel();
      await load();
    } catch (e) {
      setError(e.message?.includes("400") ? "Invalid command — check the name." : "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function remove(id) {
    if (!confirm("Delete this command?")) return;
    await api(`/api/guilds/${guildId}/commands/${id}`, { method: "DELETE" });
    if (editingId === id) cancel();
    await load();
  }

  return (
    <div className="detail-grid">
      <section className="panel">
        <h2>Slash commands</h2>
        <p className="muted small">
          Members run these as <code>/name</code>. Changes go live within ~30s.
        </p>
        {loading && <p className="muted">Loading…</p>}
        {!loading && commands.length === 0 && <p className="muted">No commands yet.</p>}
        <ul className="list">
          {commands.map((c) => (
            <li key={c.id} className="list-row">
              <span className="glyph">/</span>
              <span className="list-name">{c.name}</span>
              {!c.enabled && <span className="badge">Disabled</span>}
              <button className="btn-ghost xs" onClick={() => startEdit(c)}>Edit</button>
              <button className="btn-ghost xs danger" onClick={() => remove(c.id)}>Delete</button>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <h2>{editingId ? "Edit command" : "New command"}</h2>
        {error && <div className="alert">{error}</div>}
        <label className="field">
          <span>Name</span>
          <div className="prefixed">
            <span className="prefix">/</span>
            <input
              value={draft.name}
              maxLength={32}
              placeholder="rules"
              onChange={(e) => setDraft({ ...draft, name: e.target.value.toLowerCase() })}
            />
          </div>
          <small className="muted">Lowercase letters, numbers, - or _ (max 32).</small>
        </label>
        <label className="field">
          <span>Description</span>
          <input
            value={draft.description}
            maxLength={100}
            onChange={(e) => setDraft({ ...draft, description: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Response</span>
          <textarea
            rows={4}
            value={draft.response}
            maxLength={2000}
            placeholder="The text Guildizer replies with…"
            onChange={(e) => setDraft({ ...draft, response: e.target.value })}
          />
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={draft.enabled}
            onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
          />
          Enabled
        </label>
        <div className="form-actions">
          <button className="btn-primary" onClick={save} disabled={saving || !draft.name}>
            {saving ? "Saving…" : editingId ? "Update" : "Create"}
          </button>
          {editingId && (
            <button className="btn-ghost" onClick={cancel}>
              Cancel
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
