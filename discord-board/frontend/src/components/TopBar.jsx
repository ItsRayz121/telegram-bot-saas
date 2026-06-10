import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function TopBar() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();

  async function handleSignOut() {
    await signOut();
    navigate("/login", { replace: true });
  }

  return (
    <header className="topbar">
      <Link to="/dashboard" className="topbar-brand">
        Guild<span>izer</span>
      </Link>
      {user && (
        <div className="topbar-user">
          {user.is_admin && (
            <Link to="/admin" className="btn-ghost">Admin</Link>
          )}
          {user.avatar_url && <img src={user.avatar_url} alt="" className="avatar" />}
          <span className="topbar-name">{user.global_name || user.username}</span>
          <button className="btn-ghost" onClick={handleSignOut}>
            Sign out
          </button>
        </div>
      )}
    </header>
  );
}
