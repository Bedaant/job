// The content-script -> backend proxy's rules (LIVE-FORM-TEST.md bug #1). Pure,
// so `node --test` covers them; apiProxy.ts is the chrome glue.
//
// Why a proxy: a content script's fetch carries the EMPLOYER page's origin and is
// CORS-checked, so every call to the API from a Greenhouse/Lever/Ashby page failed.
// The service worker fetches from the extension origin, which host_permissions
// cover. The proxy is deliberately not a generic fetch: exact paths, one method
// each, fixed host (API_BASE_URL), and the bearer token is attached by the worker
// so content scripts never hold it.

const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";

const ROUTES = [
  { method: "POST", pattern: /^\/extension\/map-fields$/, response: "json" },
  // What a fill did (labels, sources, statuses; no values), for debugging a failed form.
  { method: "POST", pattern: /^\/extension\/fill-snapshots$/, response: "json" },
  // The ADR-001/015 claim that must succeed before the one native submit.
  { method: "POST", pattern: new RegExp(`^/applications/${UUID}/claim-submission$`, "i"), response: "json" },
  { method: "GET", pattern: new RegExp(`^/profiles/${UUID}/resume\\.docx$`, "i"), response: "bytes" },
  // The user's own city, for a location typeahead that has no options until typed.
  { method: "GET", pattern: new RegExp(`^/profiles/${UUID}/basics$`, "i"), response: "json" },
];

// The route for an allow-listed (method, path), else null. Strings only: an object
// with a toString() must not slip past the regex and change underneath it.
export function allowedRoute(method, path) {
  if (typeof method !== "string" || typeof path !== "string") return null;
  return ROUTES.find((r) => r.method === method && r.pattern.test(path)) ?? null;
}

// runtime messages are JSON, so bytes cross as base64. Chunked: spreading a large
// array into String.fromCharCode overflows the call stack.
export function bytesToBase64(bytes) {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

export function base64ToBytes(base64) {
  return Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
}
