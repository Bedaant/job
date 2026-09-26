import { defineConfig } from "vitest/config";
import path from "node:path";

// `environment: "node"` on purpose: neither jsdom nor happy-dom is installed and
// installing one needs owner approval (ADR-010). So the tests here cover the
// wizard's decision logic and its HTTP contract as plain modules — which is
// where the bugs actually live — rather than rendering components.
export default defineConfig({
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts"],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, ".") },
  },
});
