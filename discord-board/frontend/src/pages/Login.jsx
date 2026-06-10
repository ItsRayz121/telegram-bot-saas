import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth";
import { loginWithDiscord } from "../api";

const ERRORS = {
  invalid_state: "Login session expired. Please try again.",
  oauth_failed: "Couldn't reach Discord. Please try again.",
  access_denied: "You cancelled the Discord authorization.",
};

export default function Login() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const error = params.get("error");

  useEffect(() => {
    if (!loading && user) navigate("/dashboard", { replace: true });
  }, [loading, user, navigate]);

  return (
    <div className="shell">
      <div className="card">
        <div className="brand">
          Guild<span>izer</span>
        </div>
        <p className="sub">Discord community &amp; server management</p>

        {error && <div className="alert">{ERRORS[error] || "Something went wrong."}</div>}

        <button className="btn-discord" onClick={loginWithDiscord} disabled={loading}>
          <DiscordMark />
          Continue with Discord
        </button>

        <p className="fineprint">
          We request <strong>identify</strong> and <strong>guilds</strong> only — to show the
          servers you manage.
        </p>
      </div>
    </div>
  );
}

function DiscordMark() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M20.317 4.369A19.79 19.79 0 0 0 15.885 3a13.6 13.6 0 0 0-.617 1.27 18.27 18.27 0 0 0-5.535 0A13.6 13.6 0 0 0 9.116 3 19.79 19.79 0 0 0 4.68 4.37C1.86 8.59 1.1 12.71 1.48 16.76a19.93 19.93 0 0 0 6.07 3.08c.49-.67.93-1.39 1.3-2.14-.71-.27-1.39-.6-2.03-.99.17-.13.34-.26.5-.4a14.26 14.26 0 0 0 12.36 0c.16.14.33.27.5.4-.64.39-1.32.72-2.03.99.37.75.81 1.47 1.3 2.14a19.9 19.9 0 0 0 6.07-3.08c.45-4.69-.77-8.78-3.7-12.39ZM8.97 14.34c-1.2 0-2.18-1.1-2.18-2.45 0-1.36.96-2.46 2.18-2.46 1.23 0 2.2 1.11 2.18 2.46 0 1.35-.96 2.45-2.18 2.45Zm6.06 0c-1.2 0-2.18-1.1-2.18-2.45 0-1.36.96-2.46 2.18-2.46 1.23 0 2.2 1.11 2.18 2.46 0 1.35-.95 2.45-2.18 2.45Z" />
    </svg>
  );
}
