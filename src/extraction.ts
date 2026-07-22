// Context vector extraction module — distills session history into 5 structured context vectors.

import type { AgentMessage } from "@earendil-works/pi-agent-core";
import type { ExtractedContext } from "./types.js";
import type { ModelCallFn } from "./core.js";

export const EXTRACTION_SYSTEM_PROMPT = [
  "You are a fast context extraction engine for a software development agent.",
  "Analyze the conversation history and extract structured context vectors into JSON.",
  "",
  "Return JSON matching this schema exactly:",
  "{",
  '  "userIntentAndMotive": "Core human goal & underlying motive",',
  '  "activeConstraintsAndGuards": "Active flags, read-only mode, commit guards, or session rules",',
  '  "verifiedFactsInventory": "Confirmed facts, file mtimes, test logs, trace findings",',
  '  "evidenceFreshnessDelta": "Modified code vs timestamp of last test or visual proof",',
  '  "clarityAndAmbiguityScore": "CLEAR" or "AMBIGUOUS",',
  '  "missingDetails": "Specific missing details if AMBIGUOUS (optional)",',
  '  "deliberationNeeded": true or false,',
  '  "deliberationReason": "Short reason explaining why full probe deliberation is or is not needed (e.g. unverified code edit, ambiguous requirement, or routine conversational query)"',
  "}",
  "",
  "Set deliberationNeeded to true if code/files were modified without test verification, if requirements are AMBIGUOUS, if tools failed, or if the user asked a complex architectural question.",
  "Set deliberationNeeded to false if the user input is a simple acknowledgment, status check, routine question, or clear step in progress with fresh evidence.",
  "",
  "Output raw JSON ONLY. No conversational prefix or markdown wrapper.",
].join("\n");

/** Safe default fallback context when extraction is skipped or fails. */
export function getDefaultExtractedContext(messages?: AgentMessage[]): ExtractedContext {
  let initialGoal = "General task execution";
  if (messages && messages.length > 0) {
    const firstUserMsg = messages.find((m) => m.role === "user");
    if (firstUserMsg && "content" in firstUserMsg && typeof firstUserMsg.content === "string") {
      initialGoal = firstUserMsg.content.slice(0, 200);
    }
  }

  return {
    userIntentAndMotive: initialGoal,
    activeConstraintsAndGuards: "Standard session rules",
    verifiedFactsInventory: "Session history available in transcript",
    evidenceFreshnessDelta: "Freshness unknown — recent history should be inspected",
    clarityAndAmbiguityScore: "CLEAR",
    deliberationNeeded: true,
    deliberationReason: "Default fallback context — full audit enabled by default",
  };
}

/** Extract 5 structured context vectors from recent messages using a fast LLM pass. */
export async function extractContextFromMessages(
  messages: AgentMessage[],
  callModel: ModelCallFn,
  signal?: AbortSignal,
): Promise<ExtractedContext> {
  if (messages.length === 0) {
    return getDefaultExtractedContext(messages);
  }

  const formattedHistory = messages
    .slice(-10)
    .map((m) => {
      const role = String(m.role).toUpperCase();
      let content = "";
      if ("command" in m && "output" in m && typeof m.output === "string") {
        content = `> ${(m as any).command}\n${(m as any).output.slice(0, 500)}`;
      } else if ("content" in m) {
        content = typeof (m as any).content === "string" ? (m as any).content : JSON.stringify((m as any).content);
      }
      return `[${role}] ${content.slice(0, 1000)}`;
    })
    .join("\n\n");

  try {
    const raw = await callModel(
      "extraction",
      EXTRACTION_SYSTEM_PROMPT,
      `Conversation History:\n\n${formattedHistory}`,
      512,
      0.2,
      signal,
    );

    const jsonText = raw.replace(/^```(?:json)?\n?/i, "").replace(/\n?```$/i, "").trim();
    const parsed = JSON.parse(jsonText);

    return {
      userIntentAndMotive: String(parsed.userIntentAndMotive || getDefaultExtractedContext(messages).userIntentAndMotive),
      activeConstraintsAndGuards: String(parsed.activeConstraintsAndGuards || "Standard session rules"),
      verifiedFactsInventory: String(parsed.verifiedFactsInventory || "Session history available"),
      evidenceFreshnessDelta: String(parsed.evidenceFreshnessDelta || "No delta recorded"),
      clarityAndAmbiguityScore: parsed.clarityAndAmbiguityScore === "AMBIGUOUS" ? "AMBIGUOUS" : "CLEAR",
      missingDetails: parsed.missingDetails ? String(parsed.missingDetails) : undefined,
      deliberationNeeded: typeof parsed.deliberationNeeded === "boolean" ? parsed.deliberationNeeded : true,
      deliberationReason: parsed.deliberationReason ? String(parsed.deliberationReason) : undefined,
    };
  } catch {
    return getDefaultExtractedContext(messages);
  }
}
