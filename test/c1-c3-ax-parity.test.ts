import { describe, expect, it } from "vitest";
import type { AgentMessage } from "@earendil-works/pi-agent-core";
import { ConsortiumCore, type ModelCallFn, type ModelCallOptions } from "../src/core.js";
import { fingerprintCacheRequest } from "../src/cache-evidence.js";
import type { ConsortiumConfig } from "../src/types.js";
import { extractionStructured } from "./extraction-structured-mock.js";

const config: ConsortiumConfig = {
  probes: [
    { role: "architect", provider: "openai", modelId: "test", systemPrompt: "Architect stage policy", roleLens: "Architect role tail" },
    { role: "clarifier", provider: "openai", modelId: "test", systemPrompt: "Clarifier stage policy", roleLens: "Clarifier role tail" },
  ],
  synthesis: { provider: "openai", modelId: "test", systemPrompt: "Synthesis" },
  maxProbeTokens: 128,
  maxSynthesisTokens: 128,
  probeTemperature: 0.7,
  synthesisTemperature: 0.2,
  probeTimeoutMs: 5_000,
  totalTimeoutMs: 10_000,
  executionMode: "parallel",
  governorMode: "smart_extractor",
};

interface CapturedCall {
  modelKey: string;
  system: string;
  user: string;
  options?: ModelCallOptions;
}

describe("shared C1/C3 AX cache prefix", () => {
  it("uses one AX system, tool schema, and history prefix before parallel C3 tails", async () => {
    const captured: CapturedCall[] = [];
    const callModel: ModelCallFn = async (modelKey, system, user, _maxTokens, _temperature, _signal, options) => {
      captured.push({ modelKey, system, user, options });
      if (modelKey === "extraction") {
        return extractionStructured({ deliberationNeeded: true });
      }
      return extractionStructured({ deliberationNeeded: false, probeContribution: "NO_CONTRIBUTION" });
    };
    const messages: AgentMessage[] = [
      { role: "user", content: "First user direction", timestamp: 1 },
      { role: "assistant", content: "Observed progress", timestamp: 2 },
      { role: "user", content: "Current user direction", timestamp: 3 },
    ];

    const result = await new ConsortiumCore(config, callModel).deliberate(messages);

    expect(result.probes.map((probe) => probe.text)).toEqual(["NO_CONTRIBUTION", "NO_CONTRIBUTION"]);
    const c1 = captured.find((call) => call.modelKey === "extraction")!;
    const c3 = captured.filter((call) => call.modelKey.startsWith("probe:"));
    expect(c3).toHaveLength(2);

    const c1Fingerprint = fingerprintCacheRequest(c1.system, c1.user, c1.options);
    expect(c1Fingerprint.historyComplete).toBe(true);
    for (const call of c3) {
      const c3Fingerprint = fingerprintCacheRequest(call.system, call.user, call.options);
      expect(call.system).toBe(c1.system);
      expect(call.options).toEqual(c1.options);
      expect(c3Fingerprint.historyComplete).toBe(true);
      expect(c3Fingerprint.prefixSha256).toBe(c1Fingerprint.prefixSha256);
      expect(c3Fingerprint.prefixBytes).toBe(c1Fingerprint.prefixBytes);
      expect(call.user.slice(0, call.user.indexOf("</historical_observed_past>") + "</historical_observed_past>".length))
        .toBe(c1.user.slice(0, c1.user.indexOf("</historical_observed_past>") + "</historical_observed_past>".length));
      expect(call.user).toContain("<c3_probe_stage>");
    }
    expect(c1.user).toContain("<c1_extraction_stage>");
  });

  it("coerces missing or invalid C3 contributions without cancelling a valid parallel peer", async () => {
    const callModel: ModelCallFn = async (modelKey) => {
      if (modelKey === "extraction") {
        return extractionStructured({ deliberationNeeded: true });
      }
      if (modelKey === "probe:0:architect") {
        const missingContribution = extractionStructured({ deliberationNeeded: false });
        delete missingContribution.functionCalls![0].arguments.probeContribution;
        return missingContribution;
      }
      if (modelKey === "probe:1:clarifier") {
        return extractionStructured({ deliberationNeeded: false, probeContribution: "WARN Verified probe fact" });
      }
      return "Synthesis";
    };

    const result = await new ConsortiumCore(config, callModel).deliberate([
      { role: "user", content: "A test direction", timestamp: 1 },
    ]);

    expect(result.probes).toEqual([
      { role: "architect", text: "NO_CONTRIBUTION" },
      { role: "clarifier", text: "WARN Verified probe fact" },
    ]);
    expect(result.synthesis).toBe("Synthesis");
    expect(result.errors).toBeUndefined();
  });
});
