// Governor decision module — decides whether full probe deliberation should run.

import type { ConsortiumConfig, ExtractedContext, GovernorMode } from "./types.js";

export interface GovernorDecision {
  /** True if full probe deliberation & synthesis should be executed. */
  shouldDeliberate: boolean;
  /** Human-readable reason explaining the decision. */
  reason: string;
}

/** Evaluate whether deliberation should run based on configuration, context, and turn state. */
export function shouldDeliberate(
  config: ConsortiumConfig,
  extractedContext?: ExtractedContext,
  turnsSinceLastAudit: number = 0,
): GovernorDecision {
  const mode: GovernorMode = config.governorMode ?? "smart_extractor";
  const maxTurnGap = config.maxTurnGap ?? 20;
  const periodicInterval = config.periodicInterval ?? 3;

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
