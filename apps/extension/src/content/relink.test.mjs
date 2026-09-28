import test from "node:test";
import assert from "node:assert/strict";

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
