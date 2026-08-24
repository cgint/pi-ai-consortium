// Guard test: pins the env-isolation invariant that test/setup-env.ts enforces.
// If a CONSORTIUM_* ambient var leaks through (setup removed, reordered, or a
// new env var added to src/config.ts without extending the setup list),
// this test fails — provided the developer's shell actually sets that var.
//
// Note: this test is only a canary under an ambient environment that sets
// the vars; in a fully clean shell it passes trivially.

import { describe, expect, it } from "vitest";
import { DEFAULT_CONFIG } from "../src/config.js";

describe("env isolation (setup-env.ts)", () => {
  it("DEFAULT_CONFIG.executionMode is the default 'serial' regardless of ambient env", () => {
    expect(DEFAULT_CONFIG.executionMode).toBe("serial");
  });

  it("DEFAULT_CONFIG.reasoning is the default 'medium' regardless of ambient env", () => {
    expect(DEFAULT_CONFIG.reasoning).toBe("medium");
  });
});
