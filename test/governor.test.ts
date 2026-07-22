import { describe, it, expect } from "vitest";
import { shouldDeliberate } from "../src/governor.js";
import type { ConsortiumConfig, ExtractedContext } from "../src/types.js";
import { DEFAULT_CONFIG } from "../src/config.js";

const baseExtractedContext: ExtractedContext = {
  userIntentAndMotive: "Test task",
  activeConstraintsAndGuards: "Standard",
  verifiedFactsInventory: "None",
  evidenceFreshnessDelta: "Fresh",
  clarityAndAmbiguityScore: "CLEAR",
  deliberationNeeded: true,
  deliberationReason: "Unverified code change detected",
};

describe("Governor Decision Engine", () => {
  it("always mode returns true regardless of turn count or context", () => {
    const config: ConsortiumConfig = {
      ...DEFAULT_CONFIG,
      probes: [],
      synthesis: { systemPrompt: "", provider: "openai", modelId: "gpt-4o" },
      governorMode: "always",
    };

    const res = shouldDeliberate(config, baseExtractedContext, 5);
    expect(res.shouldDeliberate).toBe(true);
    expect(res.reason).toContain("always");
  });

  it("manual mode returns false unless manually triggered", () => {
    const config: ConsortiumConfig = {
      ...DEFAULT_CONFIG,
      probes: [],
      synthesis: { systemPrompt: "", provider: "openai", modelId: "gpt-4o" },
      governorMode: "manual",
    };

    const res = shouldDeliberate(config, baseExtractedContext, 5);
    expect(res.shouldDeliberate).toBe(false);
    expect(res.reason).toContain("manual");
  });

  it("periodic mode triggers on every N turns", () => {
    const config: ConsortiumConfig = {
      ...DEFAULT_CONFIG,
      probes: [],
      synthesis: { systemPrompt: "", provider: "openai", modelId: "gpt-4o" },
      governorMode: "periodic",
      periodicInterval: 3,
    };

    expect(shouldDeliberate(config, baseExtractedContext, 0).shouldDeliberate).toBe(false);
    expect(shouldDeliberate(config, baseExtractedContext, 1).shouldDeliberate).toBe(false);
    expect(shouldDeliberate(config, baseExtractedContext, 2).shouldDeliberate).toBe(false);
    expect(shouldDeliberate(config, baseExtractedContext, 3).shouldDeliberate).toBe(true);
  });

  it("smart_extractor mode respects deliberationNeeded boolean from context", () => {
    const config: ConsortiumConfig = {
      ...DEFAULT_CONFIG,
      probes: [],
      synthesis: { systemPrompt: "", provider: "openai", modelId: "gpt-4o" },
      governorMode: "smart_extractor",
      maxTurnGap: 20,
    };

    const skipContext: ExtractedContext = {
      ...baseExtractedContext,
      deliberationNeeded: false,
      deliberationReason: "Routine conversational query",
    };

    const skipRes = shouldDeliberate(config, skipContext, 5);
    expect(skipRes.shouldDeliberate).toBe(false);
    expect(skipRes.reason).toBe("Routine conversational query");

    const auditRes = shouldDeliberate(config, baseExtractedContext, 5);
    expect(auditRes.shouldDeliberate).toBe(true);
    expect(auditRes.reason).toBe("Unverified code change detected");
  });

  it("smart_extractor mode forces audit when maxTurnGap is reached", () => {
    const config: ConsortiumConfig = {
      ...DEFAULT_CONFIG,
      probes: [],
      synthesis: { systemPrompt: "", provider: "openai", modelId: "gpt-4o" },
      governorMode: "smart_extractor",
      maxTurnGap: 20,
    };

    const skipContext: ExtractedContext = {
      ...baseExtractedContext,
      deliberationNeeded: false,
      deliberationReason: "Routine conversational query",
    };

    // On 20th turn gap, force audit even if deliberationNeeded is false
    const res = shouldDeliberate(config, skipContext, 20);
    expect(res.shouldDeliberate).toBe(true);
    expect(res.reason).toContain("Maximum turn gap (20) reached");
  });
});
