import { test } from "node:test";
import assert from "node:assert/strict";

import { allowedRoute, base64ToBytes, bytesToBase64 } from "./apiProxyCore.mjs";

const PROFILE = "f89e912b-1234-4abc-9def-0123456789ab";

test("only the two allow-listed endpoints pass, each with its own method", () => {
  assert.equal(allowedRoute("POST", "/extension/map-fields")?.response, "json");
  assert.equal(allowedRoute("GET", `/profiles/${PROFILE}/resume.docx`)?.response, "bytes");
});

test("everything else is refused: other paths, methods, hosts, traversal, query strings", () => {
  for (const [method, path] of [
    ["GET", "/extension/map-fields"],
    ["POST", `/profiles/${PROFILE}/resume.docx`],
    ["DELETE", "/extension/map-fields"],
    ["post", "/extension/map-fields"],
    ["POST", "/extension/map-fields?x=1"],
    ["POST", "/extension/map-fields/"],
    ["POST", "/applications/1/claim-submission"],
    ["GET", "/profiles/not-a-uuid/resume.docx"],
    ["GET", `/profiles/${PROFILE}/../answers`],
    ["GET", `/profiles/${PROFILE}/resume.docx#x`],
    ["GET", `//evil.example/profiles/${PROFILE}/resume.docx`],
    ["GET", `http://evil.example/profiles/${PROFILE}/resume.docx`],
    ["POST", "@evil.example/extension/map-fields"],
    ["POST", undefined],
    [undefined, "/extension/map-fields"],
    ["POST", { toString: () => "/extension/map-fields" }],
  ]) {
    assert.equal(allowedRoute(method, path), null, `${String(method)} ${String(path)}`);
  }
});

test("bytes survive the base64 round trip across the message boundary", () => {
  const bytes = new Uint8Array(200_000).map((_, i) => (i * 31) % 256); // more than one chunk
  assert.deepEqual(base64ToBytes(bytesToBase64(bytes)), bytes);
  assert.equal(bytesToBase64(new Uint8Array([80, 75, 3, 4])), "UEsDBA=="); // a docx starts "PK\3\4"
});
