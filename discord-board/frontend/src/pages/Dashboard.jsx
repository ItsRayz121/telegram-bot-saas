import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import TopBar from "../components/TopBar";

export default function Dashboard() {
  const [state, setState] = useState({ loading: true, guilds: [], inviteUrl: null, error: null });

  useEffect(() => {
    api("/api/guilds")
      .then((d) => setState({ loading: false, guilds: d.guilds, inviteUrl: d.invite_url, error: null }))
      .catch(() => setState({ loading: false, guilds: [], inviteUrl: null, error: "Failed to load servers." }));
  }, []);

  return (
    <div className="page">
      <TopBar />
      <main className="container">
        <div className="page-head">
          <div>
            <h1>Your servers</h1>
            <p className="muted">Servers you can manage. Add Guildizer to start configuring.</p>
          </div>
          {state.inviteUrl && (
            <a className="btn-primary" href={state.inviteUrl} target="_blank" rel="noreferrer">
              + Add to a server
            </a>
          )}
        </div>

        {state.loading && <p className="muted">Loading…</p>}
        {state.error && <div className="alert">{state.error}</div>}

        {!state.loading && !state.error && state.guilds.length === 0 && (
          <div className="empty">
            <p>No manageable servers found.</p>
            <p className="muted">
              You need the <strong>Manage Server</strong> permission, or to own the server.
            </p>
          </div>
        )}

        <div className="grid">
          {state.guilds.map((gld) => (
            <ServerCard key={gld.id} guild={gld} />
          ))}
        </div>
      </main>
    </div>
  );
}

function ServerCard({ guild }) {
  const initials = (guild.name || "?").slice(0, 2).toUpperCase();
  return (
    <div className="server-card">
      <div className="server-head">
        {guild.icon_url ? (
          <img src={guild.icon_url} alt="" className="server-icon" />
        ) : (
          <div className="server-icon placeholder">{initials}</div>
        )}
        <div className="server-meta">
          <div className="server-name">{guild.name}</div>
          <div className="server-sub muted">
            {guild.bot_present ? `${guild.member_count} members` : "Bot not added"}
            {guild.is_owner && " · Owner"}
          </div>
        </div>
      </div>
      <div className="server-actions">
        {guild.bot_present ? (
          <Link className="btn-secondary" to={`/servers/${guild.id}`}>
            Manage
          </Link>
        ) : (
          <a className="btn-primary" href={guild.invite_url} target="_blank" rel="noreferrer">
            Add Guildizer
          </a>
        )}
      </div>
    </div>
  );
}
