// Tests for configuration and probe role lenses in src/config.ts.

import { describe, expect, it } from "vitest";
import { DEFAULT_CONFIG, PROBE_SYSTEM_PROMPT, CANONICAL_PROBE_ORDER } from "../src/config.js";

describe("src/config.ts", () => {
  it("defines 5 canonical reality-grounded probes", () => {
    expect(CANONICAL_PROBE_ORDER).toEqual(["architect", "clarifier", "contrarian", "navigator", "responder"]);
    expect(DEFAULT_CONFIG.probes).toHaveLength(5);
  });

  it("PROBE_SYSTEM_PROMPT instructs reality-grounded auditing without speculation", () => {
    expect(PROBE_SYSTEM_PROMPT).toContain("OBSERVED PAST REALITY ONLY");
    expect(PROBE_SYSTEM_PROMPT).toContain("NO_CONTRIBUTION");
  });

  it("clarifier probe lens references CLARITY_AND_AMBIGUITY_SCORE", () => {
    const clarifier = DEFAULT_CONFIG.probes.find((p) => p.role === "clarifier");
    expect(clarifier).toBeDefined();
    expect(clarifier?.roleLens).toContain("CLARITY_AND_AMBIGUITY_SCORE");
  });

  it("contrarian probe lens references EVIDENCE_FRESHNESS_DELTA", () => {
    const contrarian = DEFAULT_CONFIG.probes.find((p) => p.role === "contrarian");
    expect(contrarian).toBeDefined();
    expect(contrarian?.roleLens).toContain("EVIDENCE_FRESHNESS_DELTA");
  });

  it("navigator probe lens references USER_INTENT_AND_MOTIVE", () => {
    const navigator = DEFAULT_CONFIG.probes.find((p) => p.role === "navigator");
    expect(navigator).toBeDefined();
    expect(navigator?.roleLens).toContain("USER_INTENT_AND_MOTIVE");
  });

  it("architect probe lens references ACTIVE_CONSTRAINTS_AND_GUARDS", () => {
    const architect = DEFAULT_CONFIG.probes.find((p) => p.role === "architect");
    expect(architect).toBeDefined();
    expect(architect?.roleLens).toContain("ACTIVE_CONSTRAINTS_AND_GUARDS");
  });
});
