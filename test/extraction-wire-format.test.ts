import { describe, expect, it } from "vitest";
import type { AgentMessage } from "@earendil-works/pi-agent-core";
import { ConsortiumCore, type ModelCallFn } from "../src/core.js";
import type { ConsortiumConfig } from "../src/types.js";
import { extractContextFromMessages } from "../src/extraction.js";
import { extractionStructured } from "./extraction-structured-mock.js";

const MESSAGES: AgentMessage[] = [
  { role: "user", content: "Please implement feature X with a parity test.", timestamp: 1_000 },
  { role: "assistant", content: "Working on it.", timestamp: 2_000 },
];

describe("AX extraction structured-output contract", () => {
  it("requires AX's output function and parses its typed arguments on the first call", async () => {
    let receivedOptions: unknown;
    let callCount = 0;
    const mockCallFn: ModelCallFn = async (_key, _system, _user, _max, _temperature, _signal, options) => {
      callCount++;
      receivedOptions = options;
      return extractionStructured({
        userRequirements: ["Structured extraction"],
        controlBoundaries: ["schema required"],
        deliberationNeeded: false,
      });
    };

    const context = await extractContextFromMessages(MESSAGES, mockCallFn);

    expect(callCount).toBe(1);
    expect(receivedOptions).toMatchObject({
      tools: [{
        name: "__axOutput",
        constrainedSampling: { type: "json_schema", strict: "require" },
      }],
    });
    expect(context.userRequirements).toEqual(["Structured extraction"]);
    expect(context.controlBoundaries).toEqual(["schema required"]);
  });

  it("rejects a text-only response instead of falling back to AX labeled-text parsing", async () => {
    const textOnlyCallFn: ModelCallFn = async () => "User Requirements: [\"not structured\"]";

    await expect(extractContextFromMessages(MESSAGES, textOnlyCallFn))
      .rejects.toThrow('Structured AX extraction response must contain exactly one "__axOutput" output function call');
  });
});

describe("AX extraction transport parity", () => {
  const PIPELINE_CONFIG: ConsortiumConfig = {
    probes: [{ role: "clarifier", provider: "openai", modelId: "gpt-4o-mini", systemPrompt: "Clarify", roleLens: "## Lens: clarify" }],
    synthesis: { provider: "openai", modelId: "gpt-4o-mini", systemPrompt: "Synthesize" },
    maxProbeTokens: 256,
    maxSynthesisTokens: 256,
    probeTemperature: 0.7,
    synthesisTemperature: 0.3,
    probeTimeoutMs: 5000,
    totalTimeoutMs: 10000,
    executionMode: "serial",
    governorMode: "smart_extractor",
  };

  it("passes the caller AbortSignal through structured extraction", async () => {
    const controller = new AbortController();
    let receivedSignal: AbortSignal | undefined;
    const callModel: ModelCallFn = async (_key, _system, _user, _max, _temperature, signal) => {
      receivedSignal = signal;
      return extractionStructured({ userRequirements: ["ok"], deliberationNeeded: false });
    };

    await extractContextFromMessages(MESSAGES, callModel, undefined, controller.signal);

    expect(receivedSignal).toBeDefined();
    controller.abort();
    expect(receivedSignal!.aborted).toBe(true);
  });

  it("passes extraction token and temperature configuration through the transport", async () => {
    let receivedMaxTokens: number | undefined;
    let receivedTemperature: number | undefined;
    const callModel: ModelCallFn = async (_key, _system, _user, maxTokens, temperature) => {
      receivedMaxTokens = maxTokens;
      receivedTemperature = temperature;
      return extractionStructured({ userRequirements: ["ok"], deliberationNeeded: false });
    };

    await extractContextFromMessages(MESSAGES, callModel);

    expect(receivedMaxTokens).toBe(1024);
    expect(receivedTemperature).toBe(0.2);
  });

  it("reports the initial attempt when strict structured output fails", async () => {
    let extractionCalls = 0;
    const callModel: ModelCallFn = async (modelKey) => {
      if (modelKey === "extraction") {
        extractionCalls++;
        return "text-only output";
      }
      return "NO_CONTRIBUTION";
    };

    const result = await new ConsortiumCore(PIPELINE_CONFIG, callModel).deliberate(MESSAGES);

    expect(extractionCalls).toBe(1);
    expect(result.extractionAttempts).toBe(1);
    expect(result.errors?.[0]).toContain("exactly one \"__axOutput\" output function call");
  });

  it("makes one structured extraction call through the full deliberate pipeline", async () => {
    const callKeys: string[] = [];
    const callModel: ModelCallFn = async (modelKey) => {
      callKeys.push(modelKey);
      if (modelKey === "extraction") {
        return {
          ...extractionStructured({ userRequirements: ["one call"], deliberationNeeded: false }),
          usage: { input: 2215, output: 126, cacheRead: 0, cacheWrite: 0, totalTokens: 2341, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
        };
      }
      return "NO_CONTRIBUTION";
    };

    const result = await new ConsortiumCore(PIPELINE_CONFIG, callModel).deliberate(MESSAGES);

    expect(callKeys.filter((key) => key === "extraction")).toHaveLength(1);
    expect(result.extractionAttempts).toBe(1);
    expect(result.extractionDurationMs).toEqual(expect.any(Number));
    expect(result.extractionDurationMs).toBeGreaterThanOrEqual(0);
    expect(result.extractionTokenUsage).toEqual({ input: 2215, output: 126 });
  });
});
