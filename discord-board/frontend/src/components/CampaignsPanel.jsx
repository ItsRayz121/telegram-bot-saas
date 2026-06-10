import { useEffect, useState } from "react";
import { api } from "../api";

const TEXT_TYPES = new Set([0, 5]);
const TYPES = ["proof_collection", "content_submission", "social_task", "raid"];
const VMODES = ["manual", "honor", "link"];

export default function CampaignsPanel({ guildId, channels }) {
  const [campaigns, setCampaigns] = useState([]);
  const [plan, setPlan] = useState("free");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [creating, setCreating] = useState(false);

  const textChannels = (channels || []).filter((c) => TEXT_TYPES.has(c.type));

  async function load() {
    setLoading(true);
    try {
      const d = await api(`/api/guilds/${guildId}/campaigns`);
      setCampaigns(d.campaigns);
      setPlan(d.plan);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guildId]);

  if (selected) {
    return (
      <CampaignDetail
        guildId={guildId}
        campaignId={selected}
        channels={textChannels}
        plan={plan}
        onBack={() => { setSelected(null); load(); }}
      />
    );
  }

  return (
    <section className="panel">
      <div className="page-head" style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>Campaigns</h2>
        <button className="btn-primary" onClick={() => setCreating((v) => !v)}>
          {creating ? "Close" : "+ New campaign"}
        </button>
      </div>

      {creating && (
        <CreateForm
          guildId={guildId}
          channels={textChannels}
          onCreated={() => { setCreating(false); load(); }}
        />
      )}

      {loading && <p className="muted">Loading…</p>}
      {!loading && campaigns.length === 0 && <p className="muted">No campaigns yet.</p>}

      <ul className="list">
        {campaigns.map((c) => (
          <li key={c.id} className="list-row campaign-row" onClick={() => setSelected(c.id)}>
            <span className={`tag status-${c.status}`}>{c.status}</span>
            <span className="list-name">{c.title}</span>
            <span className="muted small">{c.task_count} tasks</span>
            <span className="muted small">
              {c.counts.verified}✓ / {c.counts.pending}⏳
            </span>
          </li>
        ))}
      </ul>
      {plan !== "pro" && (
        <p className="muted small" style={{ marginTop: 12 }}>
          Free plan: 1 active campaign. Campaign leaderboards are Pro.
        </p>
      )}
    </section>
  );
}

function CreateForm({ guildId, channels, onCreated }) {
  const [d, setD] = useState({
    title: "", type: "proof_collection", verification_mode: "manual",
    description: "", reward_xp: 50, channel_id: "", one_per_user: true,
  });
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  async function create() {
    setSaving(true);
    setError(null);
    try {
      await api(`/api/guilds/${guildId}/campaigns`, { method: "POST", body: JSON.stringify(d) });
      onCreated();
    } catch {
      setError("Could not create campaign.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="create-box">
      {error && <div className="alert">{error}</div>}
      <label className="field"><span>Title</span>
        <input value={d.title} maxLength={200} onChange={(e) => setD({ ...d, title: e.target.value })} /></label>
      <div className="two-col">
        <label className="field"><span>Type</span>
          <select value={d.type} onChange={(e) => setD({ ...d, type: e.target.value })}>
            {TYPES.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
          </select></label>
        <label className="field"><span>Verification</span>
          <select value={d.verification_mode} onChange={(e) => setD({ ...d, verification_mode: e.target.value })}>
            {VMODES.map((m) => <option key={m} value={m}>{m}</option>)}
          </select></label>
      </div>
      <label className="field"><span>Description</span>
        <textarea rows={2} value={d.description} maxLength={2000} onChange={(e) => setD({ ...d, description: e.target.value })} /></label>
      <div className="two-col">
        <label className="field"><span>Reward XP</span>
          <input type="number" min={0} value={d.reward_xp} onChange={(e) => setD({ ...d, reward_xp: Number(e.target.value) })} /></label>
        <label className="field"><span>Announce channel</span>
          <select value={d.channel_id} onChange={(e) => setD({ ...d, channel_id: e.target.value })}>
            <option value="">— none (set later) —</option>
            {channels.map((c) => <option key={c.id} value={c.id}># {c.name}</option>)}
          </select></label>
      </div>
      <label className="check">
        <input type="checkbox" checked={d.one_per_user} onChange={(e) => setD({ ...d, one_per_user: e.target.checked })} />
        One submission per user
      </label>
      <div className="form-actions">
        <button className="btn-primary" onClick={create} disabled={saving || !d.title.trim()}>
          {saving ? "Creating…" : "Create campaign"}
        </button>
      </div>
    </div>
  );
}

function CampaignDetail({ guildId, campaignId, channels, plan, onBack }) {
  const base = `/api/guilds/${guildId}/campaigns/${campaignId}`;
  const [c, setC] = useState(null);
  const [subs, setSubs] = useState([]);
  const [board, setBoard] = useState(null);
  const [task, setTask] = useState({ title: "", reward_xp: 25, verification_mode: "manual", task_url: "" });
  const [msg, setMsg] = useState(null);

  async function load() {
    const data = await api(base);
    setC(data);
    const s = await api(`${base}/submissions?status=pending`);
    setSubs(s.submissions);
  }
  useEffect(() => {
    load(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId]);

  async function patch(body) {
    try {
      const data = await api(base, { method: "PUT", body: JSON.stringify(body) });
      setC((prev) => ({ ...prev, ...data }));
      setMsg(null);
    } catch (e) {
      setMsg(e.status === 402 ? "Free plan allows 1 active campaign — upgrade to Pro." : "Update failed.");
    }
  }
  async function addTask() {
    if (!task.title.trim()) return;
    await api(`${base}/tasks`, { method: "POST", body: JSON.stringify(task) });
    setTask({ title: "", reward_xp: 25, verification_mode: "manual", task_url: "" });
    load();
  }
  async function delTask(tid) {
    await api(`${base}/tasks/${tid}`, { method: "DELETE" });
    load();
  }
  async function review(sid, action) {
    await api(`${base}/submissions/${sid}/review`, { method: "POST", body: JSON.stringify({ action }) });
    load();
  }
  async function post() {
    try {
      await api(`${base}/post`, { method: "POST" });
      setMsg("Queued — the bot will post within ~20s.");
    } catch (e) {
      setMsg(e.status === 400 ? "Set an announce channel first." : "Post failed.");
    }
  }
  async function loadBoard() {
    try {
      const d = await api(`${base}/leaderboard`);
      setBoard(d.leaderboard);
    } catch (e) {
      setMsg(e.status === 402 ? "Campaign leaderboards are a Pro feature." : "Failed to load.");
    }
  }

  if (!c) return <p className="muted">Loading…</p>;

  return (
    <div>
      <button className="back-link" onClick={onBack}>← All campaigns</button>
      {msg && <div className="alert">{msg}</div>}

      <div className="detail-grid">
        <section className="panel">
          <h2>{c.title}</h2>
          <p className="muted small">
            <span className={`tag status-${c.status}`}>{c.status}</span> · {c.type.replace("_", " ")} · {c.verification_mode}
          </p>
          <label className="field"><span>Announce channel</span>
            <select value={c.channel_id || ""} onChange={(e) => patch({ channel_id: e.target.value || null })}>
              <option value="">— none —</option>
              {channels.map((ch) => <option key={ch.id} value={ch.id}># {ch.name}</option>)}
            </select></label>
          <div className="form-actions" style={{ flexWrap: "wrap" }}>
            {c.status !== "active" && <button className="btn-primary" onClick={() => patch({ status: "active" })}>Activate</button>}
            {c.status === "active" && <button className="btn-secondary" onClick={() => patch({ status: "paused" })}>Pause</button>}
            {c.status === "active" && <button className="btn-secondary" onClick={post}>Re-post</button>}
            <button className="btn-secondary" onClick={() => patch({ status: "closed" })}>Close</button>
          </div>
          {c.post_status === "posted" && <p className="muted small">Posted ✓</p>}
          {c.post_status === "failed" && <p className="lockdown-on">Post failed: {c.post_error}</p>}
        </section>

        <section className="panel">
          <h2>Tasks</h2>
          {c.tasks.length === 0 && <p className="muted small">No tasks — this is a single-task campaign.</p>}
          <ul className="list">
            {c.tasks.map((t) => (
              <li key={t.id} className="list-row">
                <span className="list-name">{t.title}</span>
                <span className="badge">{t.reward_xp} XP</span>
                <span className="muted small">{t.verification_mode}</span>
                <button className="btn-ghost xs danger" onClick={() => delTask(t.id)}>✕</button>
              </li>
            ))}
          </ul>
          <div className="create-box">
            <label className="field"><span>Add task</span>
              <input placeholder="Task title" value={task.title} onChange={(e) => setTask({ ...task, title: e.target.value })} /></label>
            <div className="two-col">
              <label className="field"><span>Reward XP</span>
                <input type="number" min={0} value={task.reward_xp} onChange={(e) => setTask({ ...task, reward_xp: Number(e.target.value) })} /></label>
              <label className="field"><span>Verification</span>
                <select value={task.verification_mode} onChange={(e) => setTask({ ...task, verification_mode: e.target.value })}>
                  {VMODES.map((m) => <option key={m} value={m}>{m}</option>)}
                </select></label>
            </div>
            <label className="field"><span>Task link (optional)</span>
              <input placeholder="https://…" value={task.task_url} onChange={(e) => setTask({ ...task, task_url: e.target.value })} /></label>
            <button className="btn-secondary" onClick={addTask} disabled={!task.title.trim()}>Add task</button>
          </div>
        </section>
      </div>

      <section className="panel" style={{ marginTop: 20 }}>
        <h2>Pending submissions ({subs.length})</h2>
        {subs.length === 0 && <p className="muted">Nothing to review.</p>}
        <ul className="list">
          {subs.map((s) => (
            <li key={s.id} className="list-row">
              <span className="list-name">{s.username || s.user_id}</span>
              <span className="muted small feed-detail">{s.proof?.value || "(no proof text)"}</span>
              <button className="btn-ghost xs" onClick={() => review(s.id, "verify")}>Verify</button>
              <button className="btn-ghost xs danger" onClick={() => review(s.id, "reject")}>Reject</button>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel" style={{ marginTop: 20 }}>
        <div className="page-head" style={{ marginBottom: 12 }}>
          <h2 style={{ margin: 0 }}>Leaderboard {plan !== "pro" && <span className="badge">Pro</span>}</h2>
          <button className="btn-secondary" onClick={loadBoard}>Load</button>
        </div>
        {board && board.length === 0 && <p className="muted">No verified submissions yet.</p>}
        {board && (
          <ul className="list">
            {board.map((r) => (
              <li key={r.user_id} className="list-row">
                <span className="rank-badge">#{r.rank}</span>
                <span className="list-name">{r.username || r.user_id}</span>
                <span className="badge">{r.verified}✓</span>
                <span className="muted small">{r.xp_earned} XP</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
