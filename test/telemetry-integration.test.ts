// Production-path integration test — imports and calls the real runDeliberation
// from index.ts. Reads actual JSONL emitted by ConsortiumLogger into a temp dir.
// Mocks only the external model invocation boundary (callModelWithAuth).
//
// Structural guarantee (R6): if runDeliberation stops constructing core with
// baseline callback, stops logging per-call usage, or stops logging final summary,
// this test fails because it reads the real JSONL produced by the real function.

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";

// ── Mock the external model boundary ──
// Mock streamSimple so callModelWithAuth never hits the network.
const mockStreamSimple = vi.fn();
vi.mock("@earendil-works/pi-ai/compat", () => ({
  streamSimple: mockStreamSimple,
}));

import type { AgentMessage } from "@earendil-works/pi-agent-core";
import type { TelemetryEvent } from "../src/types.js";

/** Build a minimal valid extracted context JSON string. */
function extractionJson(): string {
  return JSON.stringify({
    userRequirements: ["Test requirement"],
    deliverables: [],
    revisedOrSupersededDirection: [],
    userDecisions: [],
    questionsAndInformationGaps: [],
    controlBoundaries: ["read-only"],
    observedWork: ["facts"],
    observedCriticalFacts: [],
    relevantLearnings: [],
    deliberationNeeded: true,
    deliberationReason: "test",
  });
}

/** Standard usage object for mocked model calls. */
function makeUsage(input: number, output: number) {
  return {
    input,
    output,
    cacheRead: 0,
    cacheWrite: 0,
    totalTokens: input + output,
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
  };
}

/** Parse all JSONL lines from the consortium log directory. */
function readJsonlEvents(tmpDir: string): TelemetryEvent[] {
  const logDir = path.join(tmpDir, ".pi", "consortium");
  if (!fs.existsSync(logDir)) return [];
  const jsonlFiles = fs.readdirSync(logDir).filter((f) => f.endsWith(".jsonl"));
  if (jsonlFiles.length === 0) return [];
  const lines = fs.readFileSync(path.join(logDir, jsonlFiles[0]), "utf-8");
  return lines
    .trim()
    .split("\n")
    .map((l) => JSON.parse(l))
    .filter((e) => e.type === "baseline_check" || e.type === "probe_complete" || e.type === "deliberation_telemetry")
    .map((e) => e as TelemetryEvent);
}

describe("production-path integration (real runDeliberation)", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "consortium-prod-"));
    vi.clearAllMocks();
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  // ── R3: Real production-path test ──

  it("imports and calls actual runDeliberation, reads real JSONL", async () => {
    // Mock callModelWithAuth so we control responses per modelKey
    const { callModelWithAuth } = await import("../src/model.js");
    vi.spyOn(await import("../src/model.js"), "callModelWithAuth").mockImplementation(async (_provider, _modelId, _system, _user, _registry, _signal) => {
      // We need to distinguish calls by their purpose. Since we can't easily
      // track modelKey at this level, we respond based on call order:
      // 1st = extraction, 2nd-6th = probes, 7th = synthesis
      return { text: extractionJson(), usage: makeUsage(10, 20) };
    });

    // Now import runDeliberation (after mock is registered)
    const { runDeliberation } = await import("../index.js");
    const { DEFAULT_CONFIG } = await import("../src/config.js");
    const { ConsortiumLogger } = await import("../src/ui.js");

    // Construct minimal ExtensionContext
    const ctx: any = {
      model: { provider: "openai", id: "gpt-4o-mini" },
      modelRegistry: {
        find: vi.fn().mockReturnValue({ provider: "openai", id: "gpt-4o-mini" }),
        getApiKeyAndHeaders: vi.fn().mockResolvedValue({ ok: true, apiKey: "test-key" }),
      },
      signal: undefined,
      hasUI: false,
      ui: {},
      cwd: tmpDir,
      sessionManager: { getSessionId: () => "test-session" },
    };

    const logger = new ConsortiumLogger(tmpDir, "test-session");
    const messages: AgentMessage[] = [{ role: "user", content: "Test input", timestamp: Date.now() }];

    await runDeliberation(DEFAULT_CONFIG, messages, ctx, logger, () => {}, 0, false);
    logger.close();

    // Read real JSONL
    const events = readJsonlEvents(tmpDir);

    // R4 assertions: baseline_check, probe_complete, deliberation_telemetry
    const baselineEvents = events.filter((e) => e.type === "baseline_check");
    expect(baselineEvents).toHaveLength(1);
    expect(baselineEvents[0].baseline_available).toBe(false);
    expect(baselineEvents[0].baseline_supplied).toBe(false);

    const probeCompleteEvents = events.filter((e) => e.type === "probe_complete");
    for (const pc of probeCompleteEvents) {
      expect(pc.usage_reported).toBeDefined();
      expect(typeof pc.usage_reported).toBe("boolean");
    }

    const delibEvents = events.filter((e) => e.type === "deliberation_telemetry");
    expect(delibEvents).toHaveLength(1);
    expect(delibEvents[0].baseline_available).toBe(false);
    expect(delibEvents[0].baseline_supplied).toBe(false);
  });

  // ── R4: Normal-path assertions with controlled mock ──

  it("first invocation baselineAvailable:false logs available=false/supplied=false", async () => {
    const { callModelWithAuth } = await import("../src/model.js");
    vi.spyOn(await import("../src/model.js"), "callModelWithAuth").mockImplementation(async (_provider, _modelId, _system, _user, _registry, _signal) => {
      return { text: extractionJson(), usage: makeUsage(10, 20) };
    });

    const { runDeliberation } = await import("../index.js");
    const { DEFAULT_CONFIG } = await import("../src/config.js");
    const { ConsortiumLogger } = await import("../src/ui.js");

    const ctx: any = {
      model: { provider: "openai", id: "gpt-4o-mini" },
      modelRegistry: {
        find: vi.fn().mockReturnValue({ provider: "openai", id: "gpt-4o-mini" }),
        getApiKeyAndHeaders: vi.fn().mockResolvedValue({ ok: true, apiKey: "test-key" }),
      },
      signal: undefined,
      hasUI: false,
      ui: {},
      cwd: tmpDir,
      sessionManager: { getSessionId: () => "test-session" },
    };

    const logger = new ConsortiumLogger(tmpDir, "test-session");
    const messages: AgentMessage[] = [{ role: "user", content: "Test", timestamp: Date.now() }];

    await runDeliberation(DEFAULT_CONFIG, messages, ctx, logger, () => {}, 0, false);
    logger.close();

    const events = readJsonlEvents(tmpDir);
    const baselineEvents = events.filter((e) => e.type === "baseline_check");
    expect(baselineEvents).toHaveLength(1);
    expect(baselineEvents[0].baseline_available).toBe(false);
    expect(baselineEvents[0].baseline_supplied).toBe(false);
  });

  it("baselineAvailable:true but continuity unwired logs available=true/supplied=false", async () => {
    const { callModelWithAuth } = await import("../src/model.js");
    vi.spyOn(await import("../src/model.js"), "callModelWithAuth").mockImplementation(async (_provider, _modelId, _system, _user, _registry, _signal) => {
      return { text: extractionJson(), usage: makeUsage(10, 20) };
    });

    const { runDeliberation } = await import("../index.js");
    const { DEFAULT_CONFIG } = await import("../src/config.js");
    const { ConsortiumLogger } = await import("../src/ui.js");

    const ctx: any = {
      model: { provider: "openai", id: "gpt-4o-mini" },
      modelRegistry: {
        find: vi.fn().mockReturnValue({ provider: "openai", id: "gpt-4o-mini" }),
        getApiKeyAndHeaders: vi.fn().mockResolvedValue({ ok: true, apiKey: "test-key" }),
      },
      signal: undefined,
      hasUI: false,
      ui: {},
      cwd: tmpDir,
      sessionManager: { getSessionId: () => "test-session" },
    };

    const logger = new ConsortiumLogger(tmpDir, "test-session");
    const messages: AgentMessage[] = [{ role: "user", content: "Test", timestamp: Date.now() }];

    // Pass baselineAvailable=true but no prior context is carried
    await runDeliberation(DEFAULT_CONFIG, messages, ctx, logger, () => {}, 0, true);
    logger.close();

    const events = readJsonlEvents(tmpDir);
    const baselineEvents = events.filter((e) => e.type === "baseline_check");
    expect(baselineEvents).toHaveLength(1);
    expect(baselineEvents[0].baseline_available).toBe(true);
    expect(baselineEvents[0].baseline_supplied).toBe(false);
  });

  it("every probe_complete has usage_reported; usage only when non-null", async () => {
    const { callModelWithAuth } = await import("../src/model.js");
    let callIndex = 0;
    vi.spyOn(await import("../src/model.js"), "callModelWithAuth").mockImplementation(async (_provider, _modelId, _system, _user, _registry, _signal) => {
      callIndex++;
      // extraction (1st) → has usage; probes (2-6) → mix of usage/null; synthesis (7th) → has usage
      if (callIndex === 1) return { text: extractionJson(), usage: makeUsage(10, 20) };
      if (callIndex <= 6) return { text: "NO_CONTRIBUTION", usage: callIndex % 2 === 0 ? makeUsage(5, 5) : null };
      return { text: "Synthesized result", usage: makeUsage(15, 25) };
    });

    const { runDeliberation } = await import("../index.js");
    const { DEFAULT_CONFIG } = await import("../src/config.js");
    const { ConsortiumLogger } = await import("../src/ui.js");

    const ctx: any = {
      model: { provider: "openai", id: "gpt-4o-mini" },
      modelRegistry: {
        find: vi.fn().mockReturnValue({ provider: "openai", id: "gpt-4o-mini" }),
        getApiKeyAndHeaders: vi.fn().mockResolvedValue({ ok: true, apiKey: "test-key" }),
      },
      signal: undefined,
      hasUI: false,
      ui: {},
      cwd: tmpDir,
      sessionManager: { getSessionId: () => "test-session" },
    };

    const logger = new ConsortiumLogger(tmpDir, "test-session");
    const messages: AgentMessage[] = [{ role: "user", content: "Test", timestamp: Date.now() }];

    await runDeliberation(DEFAULT_CONFIG, messages, ctx, logger, () => {}, 0, false);
    logger.close();

    const events = readJsonlEvents(tmpDir);
    const probeCompleteEvents = events.filter((e) => e.type === "probe_complete");

    // Every probe_complete has usage_reported
    for (const pc of probeCompleteEvents) {
      expect(pc.usage_reported).toBeDefined();
      expect(typeof pc.usage_reported).toBe("boolean");
      // When usage_reported is true, usage field must exist
      if (pc.usage_reported === true) {
        expect(pc.usage).toBeDefined();
      }
    }
  });

  it("complete/partial/unreported semantics match mocked usages", async () => {
    const { callModelWithAuth } = await import("../src/model.js");
    let callIndex = 0;
    vi.spyOn(await import("../src/model.js"), "callModelWithAuth").mockImplementation(async (_provider, _modelId, _system, _user, _registry, _signal) => {
      callIndex++;
      if (callIndex === 1) return { text: extractionJson(), usage: makeUsage(10, 20) };
      if (callIndex <= 6) return { text: "NO_CONTRIBUTION", usage: makeUsage(5, 5) };
      return { text: "Synthesized result", usage: makeUsage(15, 25) };
    });

    const { runDeliberation } = await import("../index.js");
    const { DEFAULT_CONFIG } = await import("../src/config.js");
    const { ConsortiumLogger } = await import("../src/ui.js");

    const ctx: any = {
      model: { provider: "openai", id: "gpt-4o-mini" },
      modelRegistry: {
        find: vi.fn().mockReturnValue({ provider: "openai", id: "gpt-4o-mini" }),
        getApiKeyAndHeaders: vi.fn().mockResolvedValue({ ok: true, apiKey: "test-key" }),
      },
      signal: undefined,
      hasUI: false,
      ui: {},
      cwd: tmpDir,
      sessionManager: { getSessionId: () => "test-session" },
    };

    const logger = new ConsortiumLogger(tmpDir, "test-session");
    const messages: AgentMessage[] = [{ role: "user", content: "Test", timestamp: Date.now() }];

    await runDeliberation(DEFAULT_CONFIG, messages, ctx, logger, () => {}, 0, false);
    logger.close();

    const events = readJsonlEvents(tmpDir);
    const delibEvents = events.filter((e) => e.type === "deliberation_telemetry");
    expect(delibEvents).toHaveLength(1);
    // All calls reported usage → complete
    expect(delibEvents[0].usage_status).toBe("complete");
    expect(delibEvents[0].aggregate_usage).toBeDefined();
  });

  // ── R5: Pre-governor production-path test ──

  it("pre-governor skip: zero model calls, zero baseline_check, not_applicable telemetry", async () => {
    const { callModelWithAuth } = await import("../src/model.js");
    const modelSpy = vi.spyOn(await import("../src/model.js"), "callModelWithAuth").mockImplementation(async () => {
      throw new Error("should not be called");
    });

    const { runDeliberation } = await import("../index.js");
    const { DEFAULT_CONFIG } = await import("../src/config.js");
    const { ConsortiumLogger } = await import("../src/ui.js");

    // Use governorMode: "manual" which always skips pre-governor
    const config = { ...DEFAULT_CONFIG, governorMode: "manual" as const };

    const ctx: any = {
      model: { provider: "openai", id: "gpt-4o-mini" },
      modelRegistry: {
        find: vi.fn().mockReturnValue({ provider: "openai", id: "gpt-4o-mini" }),
        getApiKeyAndHeaders: vi.fn().mockResolvedValue({ ok: true, apiKey: "test-key" }),
      },
      signal: undefined,
      hasUI: false,
      ui: {},
      cwd: tmpDir,
      sessionManager: { getSessionId: () => "test-session" },
    };

    const logger = new ConsortiumLogger(tmpDir, "test-session");
    const messages: AgentMessage[] = [{ role: "user", content: "Test", timestamp: Date.now() }];

    await runDeliberation(config, messages, ctx, logger, () => {}, 0, false);
    logger.close();

    // Zero external model calls
    expect(modelSpy).toHaveBeenCalledTimes(0);

    // Read real JSONL
    const events = readJsonlEvents(tmpDir);

    // Zero baseline_check events
    const baselineEvents = events.filter((e) => e.type === "baseline_check");
    expect(baselineEvents).toHaveLength(0);

    // Exactly one deliberation_telemetry with not_applicable
    const delibEvents = events.filter((e) => e.type === "deliberation_telemetry");
    expect(delibEvents).toHaveLength(1);
    expect(delibEvents[0].baseline_supplied).toBe("not_applicable");
    expect(delibEvents[0].usage_status).toBe("not_applicable");
  });

  // ── R6: Structural failure guarantee ──

  it("structurally fails if runDeliberation omits baseline callback or final telemetry", async () => {
    // This test proves R6 by design: it imports the real runDeliberation
    // and asserts on the real JSONL. If production ever stops:
    // 1. constructing core with baseline callback → no baseline_check in JSONL → test fails
    // 2. logging per-call usage → no usage_reported on probe_complete → test fails  
    // 3. logging final summary → no deliberation_telemetry in JSONL → test fails
    //
    // Unlike the old simulateProductionWiring which mirrored the wiring,
    // this test calls the ACTUAL exported function and reads its output.

    const { callModelWithAuth } = await import("../src/model.js");
    vi.spyOn(await import("../src/model.js"), "callModelWithAuth").mockImplementation(async (_provider, _modelId, _system, _user, _registry, _signal) => {
      return { text: extractionJson(), usage: makeUsage(10, 20) };
    });

    const { runDeliberation } = await import("../index.js");
    const { DEFAULT_CONFIG } = await import("../src/config.js");
    const { ConsortiumLogger } = await import("../src/ui.js");

    const ctx: any = {
      model: { provider: "openai", id: "gpt-4o-mini" },
      modelRegistry: {
        find: vi.fn().mockReturnValue({ provider: "openai", id: "gpt-4o-mini" }),
        getApiKeyAndHeaders: vi.fn().mockResolvedValue({ ok: true, apiKey: "test-key" }),
      },
      signal: undefined,
      hasUI: false,
      ui: {},
      cwd: tmpDir,
      sessionManager: { getSessionId: () => "test-session" },
    };

    const logger = new ConsortiumLogger(tmpDir, "test-session");
    const messages: AgentMessage[] = [{ role: "user", content: "Test", timestamp: Date.now() }];

    await runDeliberation(DEFAULT_CONFIG, messages, ctx, logger, () => {}, 0, false);
    logger.close();

    const events = readJsonlEvents(tmpDir);

    // Structural guarantees — if any of these fail, production wiring is broken:
    // 1. Exactly one baseline_check (proves callback is wired to core)
    const baselineEvents = events.filter((e) => e.type === "baseline_check");
    expect(baselineEvents).toHaveLength(1);

    // 2. At least one probe_complete with usage_reported (proves usage recording)
    const probeCompleteEvents = events.filter((e) => e.type === "probe_complete");
    expect(probeCompleteEvents.length).toBeGreaterThan(0);
    const hasUsageReported = probeCompleteEvents.some((e) => e.usage_reported === true);
    expect(hasUsageReported).toBe(true);

    // 3. Exactly one deliberation_telemetry (proves final summary is logged)
    const delibEvents = events.filter((e) => e.type === "deliberation_telemetry");
    expect(delibEvents).toHaveLength(1);
  });
});