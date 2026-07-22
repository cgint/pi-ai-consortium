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
    userIntentAndMotive: "Implement XML probe payload protocol.",
    activeConstraintsAndGuards: "read-only mode active",
    verifiedFactsInventory: "src/types.ts updated",
    evidenceFreshnessDelta: "Modified 1 min ago, vitest passing",
    clarityAndAmbiguityScore: "CLEAR",
  };

  it("builds XML probe payload with explicit tags and extracted context vectors", () => {
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
    expect(xml).toContain("</current_system_timestamp>");
    expect(xml).toContain("<user_intent_motive>Implement XML probe payload protocol.</user_intent_motive>");
    expect(xml).toContain("<active_constraints_and_guards>read-only mode active</active_constraints_and_guards>");
    expect(xml).toContain("<verified_facts_inventory>src/types.ts updated</verified_facts_inventory>");
    expect(xml).toContain("<evidence_freshness_delta>Modified 1 min ago, vitest passing</evidence_freshness_delta>");
    expect(xml).toContain("<clarity_and_ambiguity_score>CLEAR</clarity_and_ambiguity_score>");
    expect(xml).toContain("</extracted_context_anchor>");
  });

  it("includes missingDetails tag when clarity score is AMBIGUOUS", () => {
    const ambiguousContext: ExtractedContext = {
      ...sampleContext,
      clarityAndAmbiguityScore: "AMBIGUOUS",
      missingDetails: "Clarify model provider override",
    };

    const xml = buildProbeInputXml(sampleMessages, ambiguousContext);
    expect(xml).toContain("<clarity_and_ambiguity_score>AMBIGUOUS</clarity_and_ambiguity_score>");
    expect(xml).toContain("<missing_details>Clarify model provider override</missing_details>");
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

  it("buildUserContextFromMessages remains available for backward compatibility", () => {
    const legacy = buildUserContextFromMessages(sampleMessages);
    expect(legacy).not.toBeNull();
    expect(legacy).toContain("Conversation context");
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

  it("formatAgentMessageContent applies head+tail cap to massive tool_result content", () => {
    const headMark = "TOOL_HEAD_OUTPUT_START";
    const tailMark = "TOOL_TAIL_OUTPUT_END";
    const hugeBody = "X".repeat(10000);
    const hugeToolResult = `${headMark}\n${hugeBody}\n${tailMark}`;

    const messageWithHugeResult: AgentMessage = {
      role: "assistant",
      content: [
        { type: "tool_result", content: hugeToolResult },
      ],
      timestamp: Date.now(),
    } as any;

    const formatted = formatAgentMessageContent(messageWithHugeResult, 500);

    expect(formatted).toContain("TOOL_HEAD_OUTPUT_START");
    expect(formatted).toContain("TOOL_TAIL_OUTPUT_END");
    expect(formatted).toContain("... [truncated");
  });
});
