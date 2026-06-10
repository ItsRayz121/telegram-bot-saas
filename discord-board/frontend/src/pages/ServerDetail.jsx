import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import TopBar from "../components/TopBar";
import SettingsPanel from "../components/SettingsPanel";
import CommandsPanel from "../components/CommandsPanel";
import ProtectionPanel from "../components/ProtectionPanel";
import LevelingPanel from "../components/LevelingPanel";
import CampaignsPanel from "../components/CampaignsPanel";
import BillingPanel from "../components/BillingPanel";

// Discord channel type enum -> label/icon (the common ones).
const CHANNEL_TYPES = {
  0: { label: "Text", glyph: "#" },
  2: { label: "Voice", glyph: "🔊" },
  4: { label: "Category", glyph: "▸" },
  5: { label: "Announcement", glyph: "📣" },
  13: { label: "Stage", glyph: "🎙" },
  15: { label: "Forum", glyph: "🗂" },
};

const TABS = ["Overview", "Settings", "Commands", "Protection", "Leveling", "Campaigns", "Billing"];

export default function ServerDetail() {
  const { id } = useParams();
  const [state, setState] = useState({ loading: true, guild: null, error: null });
  const [tab, setTab] = useState("Overview");

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

  const guild = state.guild;

  return (
    <div className="page">
      <TopBar />
      <main className="container">
        <Link to="/dashboard" className="back-link">
          ← All servers
        </Link>

        {state.loading && <p className="muted">Loading…</p>}
        {state.error && <div className="alert">{state.error}</div>}

        {guild && (
          <>
            <Header guild={guild} />
            <nav className="tabs">
              {TABS.map((t) => (
                <button
                  key={t}
                  className={`tab ${tab === t ? "active" : ""}`}
                  onClick={() => setTab(t)}
                >
                  {t}
                </button>
              ))}
            </nav>

            {tab === "Overview" && <Overview guild={guild} />}
            {tab === "Settings" && (
              <SettingsPanel guildId={id} channels={guild.channels} roles={guild.roles} />
            )}
            {tab === "Commands" && <CommandsPanel guildId={id} />}
            {tab === "Protection" && <ProtectionPanel guildId={id} channels={guild.channels} />}
            {tab === "Leveling" && <LevelingPanel guildId={id} channels={guild.channels} />}
            {tab === "Campaigns" && <CampaignsPanel guildId={id} channels={guild.channels} />}
            {tab === "Billing" && <BillingPanel guildId={id} />}
          </>
        )}
      </main>
    </div>
  );
}

function Header({ guild }) {
  const initials = (guild.name || "?").slice(0, 2).toUpperCase();
  const channelCount = (guild.channels || []).filter((c) => c.type !== 4).length;
  const roleCount = (guild.roles || []).filter((r) => r.name !== "@everyone").length;
  return (
    <div className="server-detail-head">
      {guild.icon_url ? (
        <img src={guild.icon_url} alt="" className="server-icon lg" />
      ) : (
        <div className="server-icon lg placeholder">{initials}</div>
      )}
      <div>
        <h1>{guild.name}</h1>
        <p className="muted">
          {guild.member_count} members · {channelCount} channels · {roleCount} roles
        </p>
      </div>
    </div>
  );
}

function Overview({ guild }) {
  const channels = (guild.channels || []).filter((c) => c.type !== 4);
  const roles = (guild.roles || []).filter((r) => r.name !== "@everyone");

  return (
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
  );
}
