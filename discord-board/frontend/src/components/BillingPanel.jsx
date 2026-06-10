import { useEffect, useState } from "react";
import { api } from "../api";

export default function BillingPanel({ guildId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    api(`/api/guilds/${guildId}/billing`)
      .then(setData)
      .catch(() => setMsg("Failed to load billing."))
      .finally(() => setLoading(false));
  }, [guildId]);

  async function upgrade() {
    setBusy(true);
    setMsg(null);
    try {
      const d = await api(`/api/guilds/${guildId}/billing/checkout`, { method: "POST" });
      window.location.href = d.invoice_url; // hosted NOWPayments checkout
    } catch (e) {
      setMsg(
        e.status === 503
          ? "Payments aren't configured on this instance yet."
          : "Could not start checkout. Please try again."
      );
      setBusy(false);
    }
  }

  if (loading) return <p className="muted">Loading…</p>;
  if (!data) return <div className="alert">{msg || "No billing info."}</div>;

  const pro = data.pricing.pro;

  return (
    <div className="detail-grid">
      <section className="panel">
        <h2>Plan</h2>
        <p>
          Current plan:{" "}
          <span className={`tag ${data.is_pro ? "status-active" : ""}`}>
            {data.is_pro ? "Pro" : "Free"}
          </span>
        </p>
        {data.is_pro && data.plan_expires_at && (
          <p className="muted small">Renews / expires {new Date(data.plan_expires_at).toLocaleDateString()}</p>
        )}
        {msg && <div className="alert">{msg}</div>}
        {!data.is_pro && (
          <button className="btn-primary" onClick={upgrade} disabled={busy}>
            {busy ? "Starting checkout…" : `Upgrade to Pro — $${pro.price_usd}/mo`}
          </button>
        )}
        {data.is_pro && (
          <button className="btn-secondary" onClick={upgrade} disabled={busy}>
            {busy ? "Starting…" : "Extend Pro"}
          </button>
        )}
        {!data.configured && (
          <p className="muted small" style={{ marginTop: 10 }}>
            Payments are not configured on this server instance.
          </p>
        )}
      </section>

      <section className="panel">
        <h2>{pro.name} includes</h2>
        <ul className="list">
          {pro.features.map((f) => (
            <li key={f} className="list-row">
              <span className="glyph">✓</span>
              <span className="list-name">{f}</span>
            </li>
          ))}
        </ul>
        <p className="muted small">Paid in crypto via NOWPayments. {pro.period_days}-day periods; re-ups stack.</p>
      </section>
    </div>
  );
}
