/// <reference types="vite/client" />
// Where the extension talks to the API.
//
// Build-time, not runtime: a Chrome extension has no process env, so this is substituted
// by Vite at build and baked into the bundle. Set `VITE_API_BASE_URL` when building for a
// deployed API:
//
//     VITE_API_BASE_URL=https://api.applyscout.in npm run build
//
// It previously hardcoded localhost with a comment conceding production was unsolved,
// which meant shipping required editing source. Worse, `manifest.json`'s
// `host_permissions` listed only localhost — and Chrome refuses plain HTTP for any
// non-localhost host — so a deployed API was unreachable from the extension entirely,
// failing with a permissions error rather than anything naming the cause.
//
// Any host set here must also appear in `manifest.json`'s `host_permissions`, or the
// fetch is blocked before it leaves. `src/deployConfig.test.mjs` pins both halves.
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
