import test from "node:test";
import assert from "node:assert/strict";

import { readLive, READ_LIVE_TRIES } from "./relink.mjs";
import { relink } from "./relink.mjs";

// Found live: Greenhouse's embedded board re-renders its whole form while the
// extension waits for /map-fields, so the held elements are detached.
const sig = (id, name = id, type = "text", tag = "INPUT") => ({ tag, type, id, name });

test("same shape: each old control maps to the fresh one at its index", () => {
  const old = [sig("first_name"), sig("", "q1", "radio"), sig("", "q1", "radio")];
  assert.deepEqual(relink(old, old.map((s) => ({ ...s }))), [0, 1, 2]);
});

test("different shape: matched by id; no id means no match (never guess)", () => {
  const old = [sig("first_name"), sig("email"), sig("", "q1", "radio")];
  const fresh = [sig("banner"), sig("email"), sig("first_name")];
  assert.deepEqual(relink(old, fresh), [2, 1, -1]);
});

test("same length but a changed control at an index falls back to id", () => {
  assert.deepEqual(relink([sig("a"), sig("b")], [sig("b"), sig("a")]), [1, 0]);
});

// Found live (auto-apply, embedded Greenhouse): the embed hydrates a second or more
// after load and replaces every control. A driver-opened tab starts filling on the
// server-rendered form, so every combobox was opened while detached: 0 options read,
// every dropdown low_confidence, needs_human on every pass.
test("readLive: a read that ends on detached controls is redone on the live form", async () => {
  const reads = [{ stale: true }, { stale: false }];
  let calls = 0;
  const out = await readLive(async () => reads[calls++], (r) => r.stale);
  assert.equal(calls, 2);
  assert.deepEqual(out, { stale: false });
});

test("readLive: a form that never stops changing gets READ_LIVE_TRIES reads, then the last one", async () => {
  let calls = 0;
  const out = await readLive(async () => ({ n: ++calls }), () => true);
  assert.equal(calls, READ_LIVE_TRIES);
  assert.deepEqual(out, { n: READ_LIVE_TRIES });
});

test("readLive: a live form is read once", async () => {
  let calls = 0;
  await readLive(async () => ++calls, () => false);
  assert.equal(calls, 1);
});
