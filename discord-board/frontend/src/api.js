// Tiny fetch wrapper for the Guildizer API. Always sends the session cookie.
export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5000";

export async function api(path, options = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (res.status === 401) {
    const err = new Error("unauthorized");
    err.status = 401;
    throw err;
  }
  if (!res.ok) {
    const err = new Error(`request failed: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

// Full-page redirect into the Discord OAuth flow (must be top-level navigation).
export function loginWithDiscord() {
  window.location.href = `${API_URL}/auth/discord/login`;
}

export async function logout() {
  await fetch(`${API_URL}/auth/logout`, { method: "POST", credentials: "include" });
}
