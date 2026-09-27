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
      if (stored.jc_token) {
        setToken(stored.jc_token);
        checkIn(stored.jc_token);
      }
      if (stored.jc_profile_id) setProfileId(stored.jc_profile_id);
    });
  }, []);

  // Tells the web app this extension is here (it shows "Connected" off the
  // server's last-seen stamp). limit=0 reads the queue without taking any work.
  async function checkIn(accessToken: string) {
    const resp = await fetch(`${API_BASE_URL}/extension/work-queue?limit=0`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    }).catch(() => null);
    if (resp?.status === 401) await signOut("Your session ended. Sign in again.");
  }

  async function signOut(message: string) {
    await chrome.storage.local.remove(["jc_token", "jc_profile_id"]);
    setToken(null);
    setProfileId(null);
    setStatus(message);
  }

  async function login() {
    setStatus("Signing in…");
    const resp = await fetch(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: email, password }),
    });
    if (!resp.ok) {
      setStatus("Sign-in failed. Use the same email and password as on the ApplyScout website.");
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
    setStatus(
      firstProfileId
        ? "Signed in. Press “Run apply queue” to start applying."
        : "Signed in, but your profile isn't set up yet. Finish onboarding on the ApplyScout website first.",
    );
    checkIn(access_token);
  }

  async function fillForm() {
    if (!profileId) {
      setStatus("No profile yet. Finish onboarding on the ApplyScout website first.");
      return;
    }
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) return;
    setStatus("Filling…");
    const response = await chrome.tabs.sendMessage(tab.id, { type: "jc:fill-form", profileId });
    setStatus(
      response?.ok
        ? "Filled. Check the highlighted fields before you submit."
        : "Couldn't fill this page. Reload it and try again.",
    );
  }

  // ADR-015 Phase 1: the only trigger for the apply queue. Deliberately a button
  // and not an alarm — the user is present for the session in which applications
  // go out, even though each one is no longer individually approved.
  async function runQueue() {
    setStatus("Running the apply queue…");
    const result = await chrome.runtime.sendMessage({ type: "jc:run-queue" });
    if (!result) {
      setStatus("The extension didn't answer. Close this popup, open it again, and press “Run apply queue”.");
      return;
    }
    if (result.error) {
      const error = String(result.error);
      if (/not logged in|\(401\)/.test(error)) {
        await signOut("Your session ended. Sign in again, then press “Run apply queue”.");
      } else if (/\(\d{3}\)/.test(error)) {
        setStatus("ApplyScout's server had a problem, so nothing was sent. Try again in a minute.");
      } else {
        setStatus("Couldn't reach ApplyScout. Check your internet connection, then press “Run apply queue” again.");
      }
      return;
    }
    if (result.attempted === 0) {
      setStatus("Nothing to apply to right now. Jobs appear here as your campaign finds and tailors them.");
      return;
    }
    const counts = Object.entries(result.results)
      .map(([outcome, n]) => `${n} ${outcome.replace("_", " ")}`)
      .join(", ");
    setStatus(`Attempted ${result.attempted}: ${counts || "no results reported"}.`);
  }

  return (
    <div style={{ padding: 16, width: 260, fontFamily: "system-ui, sans-serif" }}>
      <h1 style={{ fontSize: 16, margin: 0 }}>ApplyScout</h1>

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
            Sign in
          </button>
        </div>
      ) : (
        <div style={{ marginTop: 12 }}>
          <button onClick={fillForm} style={{ width: "100%", padding: 8 }}>
            Fill this form
          </button>
          <button onClick={runQueue} style={{ width: "100%", padding: 8, marginTop: 6 }}>
            Run apply queue
          </button>
          <p style={{ fontSize: 11, color: "#666", marginTop: 6 }}>
            Applies to jobs your campaign already approved, up to its daily cap.
            Keep this browser open while it runs. Anything needing your input
            goes to your review queue on the ApplyScout website.
          </p>
        </div>
      )}

      {status && (
        <p style={{ fontSize: 12, color: "#666", marginTop: 8 }}>{status}</p>
      )}
    </div>
  );
}
