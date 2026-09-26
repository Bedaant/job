// ADR-001 structural guard: "the human always clicks submit, the system
// never does" — this test makes that a property of the codebase, not a
// convention someone has to remember. Scans real extension source files (not
// dist, not node_modules) for the DOM APIs that would actually submit a
// form. Zero dependencies — Node's built-in test runner + fs, same pattern
// as fieldDecision.test.mjs.
//
// This is a developer-time gate (runs in `node --test`). formFill.content.ts
// also carries a runtime guard (patches HTMLFormElement.prototype.submit/
// requestSubmit to throw) as defense-in-depth against a dynamically
// constructed call this source-text scan could miss (e.g. el["submit"]()).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join, extname } from "node:path";

const SRC_DIR = fileURLToPath(new URL("../", import.meta.url)); // apps/extension/src/
const SCAN_EXTENSIONS = new Set([".ts", ".tsx", ".mjs", ".js"]);
const SKIP_SUFFIXES = [".test.mjs", ".d.mts", ".d.ts"];

const FORBIDDEN_PATTERNS = [
  { name: "form.submit()", regex: /\.submit\s*\(/ },
  { name: "form.requestSubmit()", regex: /\.requestSubmit\s*\(/ },
];

// Files explicitly reviewed and exempted, with the reason documented at the
// exemption site itself, not just here. Any entry added here is a
// deliberate, reviewable decision to cross ADR-001's line, not an
// accidental one.
//
// submitApprovedApplication.ts (sub-project #4, added 2026-09-26): the one
// file that performs a real submit — but only via the ORIGINAL native
// method captured before this guard patched it, and only after a real
// network call to POST /applications/{id}/claim-submission has returned
// 200 (server-side: the application must genuinely be `approved` — a human
// already clicked Approve in the review queue — and the claim atomically
// flips it to `applied` in a locked transaction so it can fire at most
// once). Read that file in full before ever adding a second entry here.
const ALLOWLIST = new Set([
  fileURLToPath(new URL("./submitApprovedApplication.ts", import.meta.url)),
]);

function walk(dir, files = []) {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === "dist") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      walk(full, files);
    } else if (SCAN_EXTENSIONS.has(extname(entry)) && !SKIP_SUFFIXES.some((s) => entry.endsWith(s))) {
      files.push(full);
    }
  }
  return files;
}

function scanForViolations(dir) {
  const violations = [];
  for (const file of walk(dir)) {
    if (ALLOWLIST.has(file)) continue;
    const content = readFileSync(file, "utf-8");
    for (const pattern of FORBIDDEN_PATTERNS) {
      if (pattern.regex.test(content)) {
        violations.push(`${file}: matches forbidden pattern "${pattern.name}"`);
      }
    }
  }
  return violations;
}

test("ADR-001: no extension source file calls form.submit() or form.requestSubmit()", () => {
  const violations = scanForViolations(SRC_DIR);
  assert.deepEqual(
    violations,
    [],
    "ADR-001 (human always clicks submit, the system never does) would be violated " +
      "by the file(s) above. If this is truly intentional it needs explicit owner " +
      "review, not a silent addition to ALLOWLIST.",
  );
});

test("the scanner itself actually detects a violation (not vacuously passing)", () => {
  const fakeFile = "synthetic-test-fixture.ts";
  const violations = [];
  const content = 'document.querySelector("form").submit();';
  for (const pattern of FORBIDDEN_PATTERNS) {
    if (pattern.regex.test(content)) violations.push(`${fakeFile}: matches "${pattern.name}"`);
  }
  assert.equal(violations.length, 1);
  assert.match(violations[0], /form\.submit\(\)/);
});
