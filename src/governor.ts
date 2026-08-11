// Governor decision module — decides whether full probe deliberation should run.

import type { ConsortiumConfig, ExtractedContext, GovernorMode } from "./types.js";

export interface GovernorDecision {
  /** True if full probe deliberation & synthesis should be executed. */
  shouldDeliberate: boolean;
  /** Human-readable reason explaining the decision. */
  reason: string;
}

/** Evaluate whether deliberation should run based on configuration, context, and turn state. */
export function hasExplicitDurableStateSupersession(currentUserTurn: string): boolean {
  const hasReplacementVerb = /\b(?:replace|replaces|replaced|replacing|supersede|supersedes|superseded|superseding|retire|retires|retired|retiring|migrate|migrates|migrated|migrating)\b/i.test(currentUserTurn);
  const hasDurableArtifact = /\bPROJECT_STATE\.md\b|\b[\w.-]+\.ya?ml\b/i.test(currentUserTurn);
  return hasReplacementVerb && hasDurableArtifact;
}

export function shouldDeliberate(
  config: ConsortiumConfig,
  extractedContext?: ExtractedContext,
  turnsSinceLastAudit: number = 0,
  currentUserTurn: string = "",
): GovernorDecision {
  const mode: GovernorMode = config.governorMode ?? "smart_extractor";
  const maxTurnGap = config.maxTurnGap ?? 20;
  const periodicInterval = config.periodicInterval ?? 10;

  if (mode === "always") {
    return {
      shouldDeliberate: true,
      reason: "Mode is 'always' — full audit enabled on every turn",
    };
  }

  if (mode === "manual") {
    return {
      shouldDeliberate: false,
      reason: "Mode is 'manual' — skipped until explicitly triggered",
    };
  }

  if (mode === "periodic") {
    if (turnsSinceLastAudit >= periodicInterval) {
      return {
        shouldDeliberate: true,
        reason: `Periodic turn interval (${periodicInterval}) reached`,
      };
    }
    return {
      shouldDeliberate: false,
      reason: `Periodic turn interval (${periodicInterval}) not reached (${turnsSinceLastAudit}/${periodicInterval})`,
    };
  }

  // mode === "smart_extractor" (default)
  if (turnsSinceLastAudit >= maxTurnGap) {
    return {
      shouldDeliberate: true,
      reason: `Maximum turn gap (${maxTurnGap}) reached — forcing periodic safety audit`,
    };
  }

  if (config.stateSupersessionGuard === true && hasExplicitDurableStateSupersession(currentUserTurn)) {
    return {
      shouldDeliberate: true,
      reason: "Explicit durable-state supersession guard",
    };
  }

  if (extractedContext) {
    if (extractedContext.deliberationNeeded === false) {
      return {
        shouldDeliberate: false,
        reason: extractedContext.deliberationReason || "Context extraction determined full probe audit is not needed",
      };
    }
    if (extractedContext.deliberationNeeded === true) {
      return {
        shouldDeliberate: true,
        reason: extractedContext.deliberationReason || "Context extraction identified active gaps or unverified changes",
      };
    }
  }

  // Fallback default if extraction data is unavailable
  return {
    shouldDeliberate: true,
    reason: "No extraction signal available — defaulting to full audit for safety",
  };
}
