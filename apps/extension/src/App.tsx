import { useEffect, useState } from "react";
import { API_BASE_URL } from "./apiConfig";

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    chrome.storage.local.get(["jc_token", "jc_profile_id"]).then((stored) => {
      if (stored.jc_token) setToken(stored.jc_token);
      if (stored.jc_profile_id) setProfileId(stored.jc_profile_id);
    });
  }, []);

  async function login() {
    setStatus("Logging in…");
    const resp = await fetch(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: email, password }),
    });
    if (!resp.ok) {
      setStatus("Login failed.");
      return;
    }
    const { access_token } = await resp.json();

    const profilesResp = await fetch(`${API_BASE_URL}/profiles`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    const profiles = profilesResp.ok ? await profilesResp.json() : [];
    const firstProfileId = profiles[0]?.id ?? null;

    await chrome.storage.local.set({ jc_token: access_token, jc_profile_id: firstProfileId });
    setToken(access_token);
    setProfileId(firstProfileId);
    setStatus(firstProfileId ? "Logged in." : "Logged in — no profile found yet.");
  }

  async function fillForm() {
    if (!profileId) {
      setStatus("No profile — create one on the dashboard first.");
      return;
    }
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) return;
    setStatus("Filling…");
    const response = await chrome.tabs.sendMessage(tab.id, { type: "jc:fill-form", profileId });
    setStatus(response?.ok ? "Done — review flagged fields before submitting." : "Could not fill this page.");
  }

  return (
    <div style={{ padding: 16, width: 260, fontFamily: "system-ui, sans-serif" }}>
      <h1 style={{ fontSize: 16, margin: 0 }}>Job Copilot</h1>

      {!token ? (
        <div style={{ marginTop: 12 }}>
          <input
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{ width: "100%", marginBottom: 6, padding: 6 }}
          />
          <input
            placeholder="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ width: "100%", marginBottom: 6, padding: 6 }}
          />
          <button onClick={login} style={{ width: "100%", padding: 6 }}>
            Log in
          </button>
        </div>
      ) : (
        <div style={{ marginTop: 12 }}>
          <button onClick={fillForm} style={{ width: "100%", padding: 8 }}>
            Fill this form
          </button>
        </div>
      )}

      {status && (
        <p style={{ fontSize: 12, color: "#666", marginTop: 8 }}>{status}</p>
      )}
    </div>
  );
}
