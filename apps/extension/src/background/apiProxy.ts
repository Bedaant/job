// Chrome glue for the content-script -> backend proxy. The rules (which paths,
// which method, how bytes cross) live in apiProxyCore.mjs and are unit-tested.
// NOT live-browser-tested (no loaded-extension access in this project).
import { API_BASE_URL } from "../apiConfig";
import { allowedRoute, bytesToBase64 } from "./apiProxyCore.mjs";

export type ApiProxyRequest = { type: "jc:api"; method: string; path: string; body?: unknown };
export type ApiProxyResponse =
  | { ok: true; status: number; json?: unknown; base64?: string; contentType?: string }
  | { ok: false; status: number; error: string };

async function proxy(message: ApiProxyRequest): Promise<ApiProxyResponse> {
  const route = allowedRoute(message.method, message.path);
  if (!route) return { ok: false, status: 0, error: `not an allowed API call: ${message.method} ${message.path}` };

  const { jc_token: token } = await chrome.storage.local.get("jc_token");
  if (!token) return { ok: false, status: 401, error: "please log in from the extension popup first" };

  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (route.method === "POST") headers["Content-Type"] = "application/json";
  const resp = await fetch(`${API_BASE_URL}${message.path}`, {
    method: route.method,
    headers,
    body: route.method === "POST" ? JSON.stringify(message.body ?? null) : undefined,
  });
  if (!resp.ok) return { ok: false, status: resp.status, error: `API ${resp.status}` };
  if (route.response === "json") return { ok: true, status: resp.status, json: await resp.json() };
  return {
    ok: true,
    status: resp.status,
    base64: bytesToBase64(new Uint8Array(await resp.arrayBuffer())),
    contentType: resp.headers.get("content-type") ?? undefined,
  };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "jc:api") return undefined;
  // Only this extension's own scripts; web pages cannot reach onMessage without
  // externally_connectable, but say so in code rather than rely on the manifest.
  if (sender.id !== chrome.runtime.id) return undefined;
  proxy(message)
    .then(sendResponse)
    .catch((error) => sendResponse({ ok: false, status: 0, error: String(error) }));
  return true; // async response
});
