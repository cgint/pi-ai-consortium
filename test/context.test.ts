// Tests for XML payload formatting and context builders in src/context.ts.

import { describe, expect, it } from "vitest";
import { buildProbeInputXml, buildUserContextFromMessages, formatAgentMessageContent, truncateHeadTail } from "../src/context.js";
import type { ExtractedContext } from "../src/types.js";
import type { AgentMessage } from "@earendil-works/pi-agent-core";

describe("src/context.ts", () => {
  const sampleMessages: AgentMessage[] = [
    { role: "user", content: "Implement XML probe payload protocol.", timestamp: Date.now() },
    { role: "assistant", content: "I will update src/context.ts.", timestamp: Date.now() },
  ];

  const sampleContext: ExtractedContext = {
    userRequirements: ["Implement XML probe payload protocol."],
    deliverables: ["Updated src/context.ts"],
    revisedOrSupersededDirection: ["Filter low-level tool errors"],
    userDecisions: ["Use 9 strategic context slots"],
    questionsAndInformationGaps: ["None — CLEAR"],
    controlBoundaries: ["Allowed paths: dev-external/pi-ai-consortium"],
    observedWork: ["Updated src/types.ts and src/extraction.ts"],
    observedCriticalFacts: ["Pass 1 Pass 2 Pass 3 pipeline active"],
    relevantLearnings: ["Operational noise pollutes probe context"],
  };

  it("builds XML probe payload with explicit tags for 9 strategic context vectors", () => {
    const xml = buildProbeInputXml(sampleMessages, sampleContext);

    expect(xml).toContain("<probe_input_payload>");
    expect(xml).toContain("</probe_input_payload>");

    expect(xml).toContain("<meta_directive>");
    expect(xml).toContain("AUDIT OBSERVED PAST REALITY ONLY");
    expect(xml).toContain("</meta_directive>");

    expect(xml).toContain("<historical_observed_past>");
    expect(xml).toContain("[USER] Implement XML probe payload protocol.");
    expect(xml).toContain("</historical_observed_past>");

    expect(xml).toContain("<extracted_context_anchor>");
    expect(xml).toContain("<current_system_timestamp>");
    expect(xml).toContain("<durable_user_intent_and_constraints>");
    expect(xml).toContain("<user_requirements>\n      • Implement XML probe payload protocol.\n    </user_requirements>");
    expect(xml).toContain("<deliverables>\n      • Updated src/context.ts\n    </deliverables>");
    expect(xml).toContain("<revised_or_superseded_direction>\n      • Filter low-level tool errors\n    </revised_or_superseded_direction>");
    expect(xml).toContain("<user_decisions>\n      • Use 9 strategic context slots\n    </user_decisions>");
    expect(xml).toContain("<control_boundaries>\n      • Allowed paths: dev-external/pi-ai-consortium\n    </control_boundaries>");
    expect(xml).toContain("</durable_user_intent_and_constraints>");

    expect(xml).toContain("<observed_execution_reality>");
    expect(xml).toContain("<observed_work>\n      • Updated src/types.ts and src/extraction.ts\n    </observed_work>");
    expect(xml).toContain("<observed_critical_facts>\n      • Pass 1 Pass 2 Pass 3 pipeline active\n    </observed_critical_facts>");
    expect(xml).toContain("<questions_and_information_gaps>\n      • None — CLEAR\n    </questions_and_information_gaps>");
    expect(xml).toContain("<relevant_learnings>\n      • Operational noise pollutes probe context\n    </relevant_learnings>");
    expect(xml).toContain("</observed_execution_reality>");
    expect(xml).toContain("</extracted_context_anchor>");
  });

  it("formatAgentMessageContent formats array content blocks cleanly", () => {
    const messageWithBlocks: AgentMessage = {
      role: "assistant",
      content: [
        { type: "text", text: "Analyzing code structure." },
        { type: "tool_use", name: "read" },
        { type: "tool_result", content: "file content sample" },
        { type: "image", mimeType: "image/png" },
      ],
      timestamp: Date.now(),
    } as any;

    const formatted = buildUserContextFromMessages([messageWithBlocks]);
    expect(formatted).toContain("Analyzing code structure.");
    expect(formatted).toContain("[tool_use: read]");
    expect(formatted).toContain("[tool_result]: file content sample");
    expect(formatted).toContain("[image: image/png]");
  });

  it("truncateHeadTail preserves both head and tail while capping total length", () => {
    const headText = "HEAD_START: Initial setup log line.";
    const tailText = "TAIL_END: Final exit code 1 build error.";
    const middleText = "M".repeat(5000);
    const fullText = `${headText}\n${middleText}\n${tailText}`;

    const truncated = truncateHeadTail(fullText, 200);

    expect(truncated).toContain("HEAD_START");
    expect(truncated).toContain("TAIL_END");
    expect(truncated).toContain("... [truncated");
    expect(truncated.length).toBeLessThanOrEqual(250);
  });
});
