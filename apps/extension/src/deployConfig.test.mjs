/**
 * DEPLOY-A.3 — the extension must be able to reach a deployed API.
 *
 * `manifest.json` listed only `http://localhost:8000/*` in `host_permissions`, and
 * `apiConfig.ts` hardcoded the same URL with a comment conceding production was unsolved.
 * Chrome refuses plain HTTP for any non-localhost host, so a deployed API was unreachable
 * from the extension at all — and `apiProxy` would have failed on every call with a
 * permissions error rather than anything that names the cause.
 *
 * These are static-text assertions on purpose. The alternative is building the extension
 * and loading it into Chrome, which is exactly the loop this check exists to avoid.
 */
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const manifest = JSON.parse(readFileSync(join(here, "..", "manifest.json"), "utf8"));
const apiConfig = readFileSync(join(here, "apiConfig.ts"), "utf8");

const PROD_HOST = "https://api.applyscout.in/*";

test("host_permissions covers the production API over HTTPS", () => {
  assert.ok(
    manifest.host_permissions.includes(PROD_HOST),
    `host_permissions must include ${PROD_HOST} or a deployed API is unreachable; got ` +
      JSON.stringify(manifest.host_permissions),
  );
});

test("host_permissions still covers localhost for development", () => {
  assert.ok(
    manifest.host_permissions.some((h) => h.includes("localhost")),
    "dropping localhost would break every developer's loop",
  );
});

test("no production host is granted over plain http", () => {
  // Chrome would reject it, and a cleartext grant to a real host is worth refusing on
  // its own merits — the extension sends the user's bearer token over it.
  for (const host of manifest.host_permissions) {
    if (host.startsWith("http://")) {
      assert.ok(
        /^http:\/\/(localhost|127\.0\.0\.1)/.test(host),
        `${host} is plain HTTP and not localhost`,
      );
    }
  }
});

test("the API base URL is build-configurable, not hardcoded", () => {
  assert.ok(
    apiConfig.includes("import.meta.env"),
    "apiConfig.ts must read a build-time value, or shipping to production needs a source edit",
  );
});

test("the API base URL still defaults to localhost", () => {
  assert.ok(
    apiConfig.includes("http://localhost:8000"),
    "an unset build var must fall back to the dev server, not to production",
  );
});

test("linkedin stays excluded from content scripts", () => {
  // Unrelated to deployment, asserted here because this file is where manifest
  // regressions will be noticed. ADR-002's boundary, and the owner's 2026-10-08 decision
  // was read-only clipping, which the content scripts do not implement.
  const [cs] = manifest.content_scripts;
  assert.ok(
    (cs.exclude_matches || []).some((m) => m.includes("linkedin.com")),
    "removing the LinkedIn exclusion is an ADR decision, not a config tweak",
  );
});
