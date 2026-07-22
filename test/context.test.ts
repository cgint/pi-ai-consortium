// Tests for XML payload formatting and context builders in src/context.ts.

import { describe, expect, it } from "vitest";
import { buildProbeInputXml, buildUserContextFromMessages } from "../src/context.js";
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

  it("buildUserContextFromMessages remains available for backward compatibility", () => {
    const legacy = buildUserContextFromMessages(sampleMessages);
    expect(legacy).not.toBeNull();
    expect(legacy).toContain("Conversation context");
  });
});
