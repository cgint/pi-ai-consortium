// Stage A telemetry tests — baseline_check, deliberation_telemetry, safeTelemetry isolation.
// No behavioral changes: telemetry records only.

import { describe, expect, it, vi } from "vitest";
import { ConsortiumCore, type ModelCallFn } from "../src/core.js";
import type { ConsortiumConfig, ExtractedContext, TelemetryEvent } from "../src/types.js";
import { extractionStructured } from "./extraction-structured-mock.js";

/** Build a minimal valid extracted context as an AX output-function call. */
function extractionJson(overrides: Partial<ExtractedContext> = {}) {
  return extractionStructured({
    userRequirements: ["Test requirement"],
    controlBoundaries: ["read-only"],
    observedWork: ["facts"],
    deliberationNeeded: true,
    deliberationReason: "test",
    ...overrides,
  });
}

const baseConfig: ConsortiumConfig = {
  probes: [
    { role: "clarifier", provider: "openai", modelId: "gpt-4o-mini", systemPrompt: "Clarify", roleLens: "## Lens: clarify" },
    { role: "contrarian", provider: "openai", modelId: "gpt-4o-mini", systemPrompt: "Challenge", roleLens: "## Lens: challenge" },
  ],
  synthesis: { provider: "openai", modelId: "gpt-4o-mini", systemPrompt: "Synthesize" },
  maxProbeTokens: 256,
  maxSynthesisTokens: 256,
  probeTemperature: 0.7,
  synthesisTemperature: 0.3,
  probeTimeoutMs: 5000,
  totalTimeoutMs: 10000,
  executionMode: "serial",
};

// ── Baseline check tests (core narrow callback) ──

describe("baseline_check telemetry", () => {
  it("emits baseline_supplied: false on first extraction (no prior context)", async () => {
    const baselines: boolean[] = [];
    const onBaseline = (bs: boolean) => baselines.push(bs);

    const callFn: ModelCallFn = async (modelKey) => {
      if (modelKey === "extraction") return extractionJson();
      return "NO_CONTRIBUTION";
    };

    const core = new ConsortiumCore(baseConfig, callFn, onBaseline);
    const messages = [{ role: "user" as const, content: "First turn", timestamp: Date.now() }];
    await core.deliberate(messages);

    expect(baselines).toHaveLength(1);
    expect(baselines[0]).toBe(false);
  });

  it("emits baseline_supplied: true when explicit previousContext is provided", async () => {
    const baselines: boolean[] = [];
    const onBaseline = (bs: boolean) => baselines.push(bs);

    const callFn: ModelCallFn = async (modelKey) => {
      if (modelKey === "extraction") return extractionJson();
      return "NO_CONTRIBUTION";
    };

    const core = new ConsortiumCore(baseConfig, callFn, onBaseline);
    const messages = [{ role: "user" as const, content: "Second turn", timestamp: Date.now() }];
    const priorContext: ExtractedContext = {
      userRequirements: ["Prior requirement"],
      deliverables: [],
      revisedOrSupersededDirection: [],
      userDecisions: [],
      questionsAndInformationGaps: [],
      controlBoundaries: [],
      observedWork: [],
      observedCriticalFacts: [],
      relevantLearnings: [],
    };
    await core.deliberate(messages, undefined, undefined, 0, priorContext);

    expect(baselines).toHaveLength(1);
    expect(baselines[0]).toBe(true);
  });

  it("emits baseline_supplied: true on second deliberation (intra-instance carry)", async () => {
    const baselines: boolean[] = [];
    const onBaseline = (bs: boolean) => baselines.push(bs);

    const callFn: ModelCallFn = async (modelKey) => {
      if (modelKey === "extraction") return extractionJson();
      return "NO_CONTRIBUTION";
    };

    const core = new ConsortiumCore(baseConfig, callFn, onBaseline);
    const msgs1 = [{ role: "user" as const, content: "Turn 1", timestamp: Date.now() }];
    await core.deliberate(msgs1);

    const msgs2 = [{ role: "user" as const, content: "Turn 2", timestamp: Date.now() }];
    await core.deliberate(msgs2);

    expect(baselines).toHaveLength(2);
    expect(baselines[0]).toBe(false); // first turn
    expect(baselines[1]).toBe(true);  // second turn uses lastExtractedContext
  });

  it("does NOT emit baseline_check when pre-governor skips extraction", async () => {
    const baselines: boolean[] = [];
    const onBaseline = (bs: boolean) => baselines.push(bs);

    const callFn: ModelCallFn = async () => {
      fail("should not call model when governor skips");
      return "";
    };

    const core = new ConsortiumCore(
      { ...baseConfig, governorMode: "periodic", periodicInterval: 10 },
      callFn,
      onBaseline,
    );
    const messages = [{ role: "user" as const, content: "Hello", timestamp: Date.now() }];
    await core.deliberate(messages, undefined, undefined, 2);

    expect(baselines).toHaveLength(0);
  });

  it("does NOT emit baseline_check when input is a plain string (no extraction)", async () => {
    const baselines: boolean[] = [];
    const onBaseline = (bs: boolean) => baselines.push(bs);

    const callFn: ModelCallFn = async () => "NO_CONTRIBUTION";
    const core = new ConsortiumCore(baseConfig, callFn, onBaseline);
    await core.deliberate("Plain string input");

    expect(baselines).toHaveLength(0);
  });
});

// ── No core deliberation_telemetry event ──

describe("core does not emit deliberation_telemetry", () => {
  it("core callback is only invoked for baseline, not for final telemetry", async () => {
    // The callback is (bs: boolean) => void, not TelemetryEvent.
    // If core tried to emit deliberation_telemetry, the callback type
    // would reject it. Verify by running a full deliberation and checking
    // the callback was called exactly once (baseline only).
    const baselines: boolean[] = [];
    const onBaseline = (bs: boolean) => baselines.push(bs);

    const callFn: ModelCallFn = async (modelKey) => {
      if (modelKey === "extraction") return extractionJson();
      if (modelKey.startsWith("probe:")) return "WARN Probe finding";
      return "Synthesized result";
    };

    const core = new ConsortiumCore(baseConfig, callFn, onBaseline);
    const messages = [{ role: "user" as const, content: "Test", timestamp: Date.now() }];
    await core.deliberate(messages);

    // Only baseline_check should fire, not deliberation_telemetry
    expect(baselines).toHaveLength(1);
    expect(baselines[0]).toBe(false);
  });
});

// ── Safe telemetry (exception isolation) tests ──

describe("baseline callback throw isolation", () => {
  it("callback throw does not alter deliberation result", async () => {
    const throwingCallback = (): void => {
      throw new Error("Baseline callback failed");
    };

    const callFn: ModelCallFn = async (modelKey) => {
      if (modelKey === "extraction") return extractionJson();
      if (modelKey.startsWith("probe:")) {
        return extractionStructured({ deliberationNeeded: false, probeContribution: "WARN Probe finding" });
      }
      return "Synthesized result";
    };

    const core = new ConsortiumCore(baseConfig, callFn, throwingCallback);
    const messages = [{ role: "user" as const, content: "Test", timestamp: Date.now() }];
    const result = await core.deliberate(messages);

    // Result should be unaffected by callback failure
    expect(result.synthesis).toBe("Synthesized result");
    expect(result.extractedContext).toBeDefined();
    expect(result.errors).toBeUndefined();
  });

  it("returned model text is byte-for-byte unchanged with callback attached", async () => {
    const exactText = "WARN Exact probe output text that must not change";
    const baselines: boolean[] = [];
    const onBaseline = (bs: boolean) => baselines.push(bs);

    const callFn: ModelCallFn = async (modelKey) => {
      if (modelKey === "extraction") return extractionJson();
      if (modelKey.startsWith("probe:")) {
        return extractionStructured({ deliberationNeeded: false, probeContribution: exactText });
      }
      return "Synthesized result";
    };

    const core = new ConsortiumCore(baseConfig, callFn, onBaseline);
    const messages = [{ role: "user" as const, content: "Test", timestamp: Date.now() }];
    const result = await core.deliberate(messages);

    expect(result.probes[0].text).toBe(exactText);
    expect(result.probes[1].text).toBe(exactText);
  });
});

// ── No callback when absent ──

describe("no-callback when absent", () => {
  it("works correctly without baseline callback", async () => {
    const callFn: ModelCallFn = async (modelKey) => {
      if (modelKey === "extraction") return extractionJson();
      if (modelKey.startsWith("probe:")) return "WARN Probe finding";
      return "Synthesized result";
    };

    // No baseline callback
    const core = new ConsortiumCore(baseConfig, callFn);
    const messages = [{ role: "user" as const, content: "Test", timestamp: Date.now() }];
    const result = await core.deliberate(messages);

    expect(result.synthesis).toBe("Synthesized result");
    expect(result.extractedContext).toBeDefined();
  });
});

// ── Existing call/order/prompt tests remain green (spot check) ──

describe("regression: existing behavior unchanged", () => {
  it("passes correct modelKey sequence to callModel", async () => {
    const keys: string[] = [];
    const callFn: ModelCallFn = async (modelKey) => {
      keys.push(modelKey);
      if (modelKey === "extraction") return extractionJson();
      return "WARN OK";
    };
    const core = new ConsortiumCore(baseConfig, callFn);
    await core.deliberate("Test");

    expect(keys).toEqual(["probe:0:clarifier", "probe:1:contrarian", "synthesis"]);
  });

  it("executes probes serially in serial mode", async () => {
    const order: string[] = [];
    const callFn: ModelCallFn = async (modelKey) => {
      order.push(`${modelKey}-start`);
      await new Promise((r) => setTimeout(r, 30));
      order.push(`${modelKey}-end`);
      return "WARN OK";
    };
    const core = new ConsortiumCore({ ...baseConfig, executionMode: "serial" }, callFn);
    await core.deliberate("Test");

    expect(order[0]).toBe("probe:0:clarifier-start");
    expect(order[1]).toBe("probe:0:clarifier-end");
    expect(order[2]).toBe("probe:1:contrarian-start");
    expect(order[3]).toBe("probe:1:contrarian-end");
  });
});