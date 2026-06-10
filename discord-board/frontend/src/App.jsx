import { useEffect, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5000";

export default function App() {
  const [state, setState] = useState({ status: "wait", label: "Connecting to API…" });

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((r) => r.json())
      .then((d) =>
        setState({
          status: d.status === "healthy" ? "ok" : "bad",
          label: `API ${d.status} · ${d.service}`,
        })
      )
      .catch(() => setState({ status: "bad", label: "API unreachable" }));
  }, []);

  return (
    <div className="shell">
      <div className="card">
        <div className="brand">
          Guild<span>izer</span>
        </div>
        <p className="sub">Discord community & server management — Phase 0</p>
        <div className="status">
          <span className={`dot ${state.status}`} />
          {state.label}
        </div>
      </div>
    </div>
  );
}
