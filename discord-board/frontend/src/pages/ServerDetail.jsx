import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import TopBar from "../components/TopBar";

// Discord channel type enum -> label/icon (the common ones).
const CHANNEL_TYPES = {
  0: { label: "Text", glyph: "#" },
  2: { label: "Voice", glyph: "🔊" },
  4: { label: "Category", glyph: "▸" },
  5: { label: "Announcement", glyph: "📣" },
  13: { label: "Stage", glyph: "🎙" },
  15: { label: "Forum", glyph: "🗂" },
};

export default function ServerDetail() {
  const { id } = useParams();
  const [state, setState] = useState({ loading: true, guild: null, error: null });

  useEffect(() => {
    api(`/api/guilds/${id}`)
      .then((d) => setState({ loading: false, guild: d, error: null }))
      .catch((e) =>
        setState({
          loading: false,
          guild: null,
          error: e.status === 403 ? "You can't manage this server." : "Failed to load server.",
        })
      );
  }, [id]);

  return (
    <div className="page">
      <TopBar />
      <main className="container">
        <Link to="/dashboard" className="back-link">
          ← All servers
        </Link>

        {state.loading && <p className="muted">Loading…</p>}
        {state.error && <div className="alert">{state.error}</div>}

        {state.guild && <ServerView guild={state.guild} />}
      </main>
    </div>
  );
}

function ServerView({ guild }) {
  const initials = (guild.name || "?").slice(0, 2).toUpperCase();
  const channels = [...(guild.channels || [])].filter((c) => c.type !== 4);
  const roles = (guild.roles || []).filter((r) => r.name !== "@everyone");

  return (
    <>
      <div className="server-detail-head">
        {guild.icon_url ? (
          <img src={guild.icon_url} alt="" className="server-icon lg" />
        ) : (
          <div className="server-icon lg placeholder">{initials}</div>
        )}
        <div>
          <h1>{guild.name}</h1>
          <p className="muted">
            {guild.member_count} members · {channels.length} channels · {roles.length} roles
          </p>
        </div>
      </div>

      <div className="detail-grid">
        <section className="panel">
          <h2>Channels</h2>
          {channels.length === 0 && <p className="muted">No channels synced yet.</p>}
          <ul className="list">
            {channels.map((c) => {
              const t = CHANNEL_TYPES[c.type] || { label: "Channel", glyph: "#" };
              return (
                <li key={c.id} className="list-row">
                  <span className="glyph">{t.glyph}</span>
                  <span className="list-name">{c.name}</span>
                  <span className="badge">{t.label}</span>
                </li>
              );
            })}
          </ul>
        </section>

        <section className="panel">
          <h2>Roles</h2>
          {roles.length === 0 && <p className="muted">No roles synced yet.</p>}
          <ul className="list">
            {roles.map((r) => (
              <li key={r.id} className="list-row">
                <span className="role-dot" style={{ background: r.color || "#99aab5" }} />
                <span className="list-name">{r.name}</span>
                {r.managed && <span className="badge">Integration</span>}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}
