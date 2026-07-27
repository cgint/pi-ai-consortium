// Tests for configuration and probe role lenses in src/config.ts.

import { describe, expect, it } from "vitest";
import { DEFAULT_CONFIG, PROBE_SYSTEM_PROMPT, CANONICAL_PROBE_ORDER, parseModelRef } from "../src/config.js";

describe("src/config.ts", () => {
  it("defines 5 canonical reality-grounded probes", () => {
    expect(CANONICAL_PROBE_ORDER).toEqual(["architect", "clarifier", "contrarian", "navigator", "responder"]);
    expect(DEFAULT_CONFIG.probes).toHaveLength(5);
  });

  it("PROBE_SYSTEM_PROMPT instructs reality-grounded auditing without speculation", () => {
    expect(PROBE_SYSTEM_PROMPT).toContain("OBSERVED PAST REALITY ONLY");
    expect(PROBE_SYSTEM_PROMPT).toContain("NO_CONTRIBUTION");
  });

  it("clarifier probe lens references questions_and_information_gaps", () => {
    const clarifier = DEFAULT_CONFIG.probes.find((p) => p.role === "clarifier");
    expect(clarifier).toBeDefined();
    expect(clarifier?.roleLens).toContain("questions_and_information_gaps");
  });

  it("contrarian probe lens references observed_work and observed_critical_facts", () => {
    const contrarian = DEFAULT_CONFIG.probes.find((p) => p.role === "contrarian");
    expect(contrarian).toBeDefined();
    expect(contrarian?.roleLens).toContain("observed_work");
    expect(contrarian?.roleLens).toContain("observed_critical_facts");
  });

  it("navigator probe lens references user_requirements and deliverables", () => {
    const navigator = DEFAULT_CONFIG.probes.find((p) => p.role === "navigator");
    expect(navigator).toBeDefined();
    expect(navigator?.roleLens).toContain("user_requirements");
    expect(navigator?.roleLens).toContain("deliverables");
  });

  it("architect probe lens references control_boundaries and user_decisions", () => {
    const architect = DEFAULT_CONFIG.probes.find((p) => p.role === "architect");
    expect(architect).toBeDefined();
    expect(architect?.roleLens).toContain("control_boundaries");
    expect(architect?.roleLens).toContain("user_decisions");
  });

  // ── parseModelRef ──

  describe("parseModelRef", () => {
    it("parses valid provider/model", () => {
      expect(parseModelRef("google/gemini-3.6-flash")).toEqual({
        provider: "google",
        modelId: "gemini-3.6-flash",
      });
    });

    it("handles model id with slashes (splits on first /)", () => {
      expect(parseModelRef("ollama/qwen3:latest")).toEqual({
        provider: "ollama",
        modelId: "qwen3:latest",
      });
    });

    it("returns undefined for undefined input", () => {
      expect(parseModelRef(undefined)).toBeUndefined();
    });

    it("returns undefined for empty string", () => {
      expect(parseModelRef("")).toBeUndefined();
    });

    it("returns undefined for whitespace-only string", () => {
      expect(parseModelRef("   ")).toBeUndefined();
    });

    it("returns undefined for missing provider (starts with /)", () => {
      expect(parseModelRef("/gemini")).toBeUndefined();
    });

    it("returns undefined for missing modelId (ends with /)", () => {
      expect(parseModelRef("google/")).toBeUndefined();
    });

    it("returns undefined for no slash at all", () => {
      expect(parseModelRef("gemini-3.6-flash")).toBeUndefined();
    });

    it("trims whitespace from input", () => {
      expect(parseModelRef("  google/gemini-3.6-flash  ")).toEqual({
        provider: "google",
        modelId: "gemini-3.6-flash",
      });
    });
  });
});
