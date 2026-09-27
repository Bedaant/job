import type { ExtensionStatus } from "./api";

// ADR-015 §3: Maggie applies from the user's own browser via the extension. The
// web app polls GET /extension/status so the user can see whether it's connected.
export const EXTENSION_POLL_MS = 4000;

export function extensionStatusView(
  status: ExtensionStatus | undefined,
  isError: boolean,
): { connected: boolean; text: string } {
  if (isError) return { connected: false, text: "Couldn't check the extension right now. Trying again…" };
  if (!status) return { connected: false, text: "Checking for the extension…" };
  if (status.connected) {
    const n = status.approved_waiting;
    return {
      connected: true,
      text: n > 0 ? `Connected ✓ · ${n} ${n === 1 ? "application" : "applications"} ready to send` : "Connected ✓",
    };
  }
  if (status.last_seen_at) {
    return {
      connected: false,
      text: "Not connected. Open the ApplyScout extension and press “Run apply queue”.",
    };
  }
  return { connected: false, text: "Waiting for the extension…" };
}
