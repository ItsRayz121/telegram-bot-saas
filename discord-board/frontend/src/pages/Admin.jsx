import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import TopBar from "../components/TopBar";

const SECTIONS = ["Overview", "Guilds", "Users", "Campaigns", "Events"];

export default function Admin() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [section, setSection] = useState("Overview");

  useEffect(() => {
    if (!loading && (!user || !user.is_admin)) navigate("/dashboard", { replace: true });
  }, [loading, user, navigate]);

  if (loading || !user) return <div className="shell"><p className="muted">Loading…</p></div>;
  if (!user.is_admin) return null;

  return (
    <div className="page">
      <TopBar />
      <div className="admin-shell">
        <nav className="admin-sidebar">
          <div className="admin-title">Admin</div>
          {SECTIONS.map((s) => (
            <button key={s} className={`admin-nav ${section === s ? "active" : ""}`} onClick={() => setSection(s)}>
              {s}
            </button>
          ))}
        </nav>
        <main className="admin-main">
          {section === "Overview" && <Overview />}
          {section === "Guilds" && <Guilds />}
          {section === "Users" && <Users />}
          {section === "Campaigns" && <Campaigns />}
          {section === "Events" && <Events />}
        </main>
      </div>
    </div>
  );
}

function useFetch(path) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    api(path).then(setData).catch(() => setError("Failed to load."));
  }, [path]);
  return [data, error, setData];
}

const STAT_LABELS = {
  guilds_total: "Servers", guilds_with_bot: "Bot installed", guilds_pro: "Pro servers",
  users_total: "Users", members_total: "Members", campaigns_total: "Campaigns",
  campaigns_active: "Active campaigns", submissions_total: "Submissions",
  submissions_verified: "Verified", protection_events_total: "Protection events",
  xp_events_total: "XP grants", subscriptions_active: "Active subs",
};

function Overview() {
  const [data, error] = useFetch("/api/admin/overview");
  if (error) return <div className="alert">{error}</div>;
  if (!data) return <p className="muted">Loading…</p>;
  return (
    <>
      <h1>Overview</h1>
      <div className="stat-grid">
        {Object.entries(STAT_LABELS).map(([k, label]) => (
          <div key={k} className="stat-card">
            <div className="stat-num">{data[k] ?? 0}</div>
            <div className="stat-label">{label}</div>
          </div>
        ))}
      </div>
    </>
  );
}

function Guilds() {
  const [data, error] = useFetch("/api/admin/guilds");
  const [sel, setSel] = useState(null);
  if (error) return <div className="alert">{error}</div>;
  if (!data) return <p className="muted">Loading…</p>;
  if (sel) return <GuildDetail guildId={sel} onBack={() => setSel(null)} />;
  return (
    <>
      <h1>Servers ({data.guilds.length})</h1>
      <table className="admin-table">
        <thead><tr><th>Name</th><th>Members</th><th>Plan</th><th>Bot</th></tr></thead>
        <tbody>
          {data.guilds.map((gd) => (
            <tr key={gd.id} onClick={() => setSel(gd.id)} className="clickable">
              <td>{gd.name}</td>
              <td>{gd.member_count}</td>
              <td><span className={`tag ${gd.is_pro ? "status-active" : ""}`}>{gd.plan}</span></td>
              <td>{gd.bot_present ? "✓" : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function GuildDetail({ guildId, onBack }) {
  const [data, setData] = useState(null);
  const [days, setDays] = useState(30);

  async function load() { setData(await api(`/api/admin/guilds/${guildId}`)); }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [guildId]);

  async function setPlan(plan) {
    await api(`/api/admin/guilds/${guildId}/plan`, { method: "POST", body: JSON.stringify({ plan, days }) });
    load();
  }
  if (!data) return <p className="muted">Loading…</p>;
  const gd = data.guild;
  return (
    <>
      <button className="back-link" onClick={onBack}>← All servers</button>
      <h1>{gd.name}</h1>
      <div className="stat-grid">
        <Stat n={data.members} l="Members" /><Stat n={data.campaigns} l="Campaigns" />
        <Stat n={data.submissions} l="Submissions" /><Stat n={data.protection_events} l="Protection events" />
      </div>
      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Plan: <span className={`tag ${gd.is_pro ? "status-active" : ""}`}>{gd.plan}</span></h2>
        <div className="form-actions">
          <input type="number" min={1} value={days} onChange={(e) => setDays(Number(e.target.value))} style={{ width: 80 }} />
          <button className="btn-primary" onClick={() => setPlan("pro")}>Grant Pro</button>
          <button className="btn-secondary" onClick={() => setPlan("free")}>Set Free</button>
        </div>
      </section>
      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Recent protection events</h2>
        {data.recent_events.length === 0 && <p className="muted">None.</p>}
        <ul className="feed">
          {data.recent_events.map((e) => (
            <li key={e.id} className="feed-row">
              <span className={`tag tag-${e.category}`}>{e.category}</span>
              <span className="feed-action">{e.action}</span>
              <span className="feed-detail">{e.detail}</span>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}

function Users() {
  const [data, error] = useFetch("/api/admin/users");
  const [sel, setSel] = useState(null);
  if (error) return <div className="alert">{error}</div>;
  if (!data) return <p className="muted">Loading…</p>;
  if (sel) return <UserDetail userId={sel} onBack={() => setSel(null)} />;
  return (
    <>
      <h1>Users ({data.users.length})</h1>
      <table className="admin-table">
        <thead><tr><th>User</th><th>Servers</th><th>ID</th></tr></thead>
        <tbody>
          {data.users.map((u) => (
            <tr key={u.id} onClick={() => setSel(u.id)} className="clickable">
              <td>{u.global_name || u.username}</td>
              <td>{u.memberships}</td>
              <td className="muted small">{u.id}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function UserDetail({ userId, onBack }) {
  const [data] = useFetch(`/api/admin/users/${userId}`);
  if (!data) return <p className="muted">Loading…</p>;
  return (
    <>
      <button className="back-link" onClick={onBack}>← All users</button>
      <h1>{data.user.global_name || data.user.username}</h1>
      <section className="panel">
        <h2>Memberships</h2>
        <ul className="list">
          {data.memberships.map((m) => (
            <li key={m.guild_id} className="list-row">
              <span className="list-name">{m.name}</span>
              {m.is_owner && <span className="badge">Owner</span>}
              {m.can_manage && <span className="badge">Manager</span>}
              <span className={`tag ${m.plan === "pro" ? "status-active" : ""}`}>{m.plan}</span>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}

function Campaigns() {
  const [data, error] = useFetch("/api/admin/campaigns");
  if (error) return <div className="alert">{error}</div>;
  if (!data) return <p className="muted">Loading…</p>;
  return (
    <>
      <h1>Campaigns ({data.campaigns.length})</h1>
      <table className="admin-table">
        <thead><tr><th>Title</th><th>Type</th><th>Status</th><th>Subs</th></tr></thead>
        <tbody>
          {data.campaigns.map((c) => (
            <tr key={c.id}>
              <td>{c.title}</td><td>{c.type.replace("_", " ")}</td>
              <td><span className={`tag status-${c.status}`}>{c.status}</span></td>
              <td>{c.submissions}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Events() {
  const [data, error] = useFetch("/api/admin/events");
  if (error) return <div className="alert">{error}</div>;
  if (!data) return <p className="muted">Loading…</p>;
  return (
    <>
      <h1>Protection events</h1>
      <ul className="feed">
        {data.events.map((e) => (
          <li key={e.id} className="feed-row">
            <span className={`tag tag-${e.category}`}>{e.category}</span>
            <span className="feed-action">{e.action}</span>
            <span className="feed-detail">{e.username ? `${e.username} — ` : ""}{e.detail}</span>
            <span className="feed-time">{new Date(e.created_at).toLocaleString()}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

function Stat({ n, l }) {
  return <div className="stat-card"><div className="stat-num">{n}</div><div className="stat-label">{l}</div></div>;
}
