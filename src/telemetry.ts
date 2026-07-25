// Telemetry utilities — usage accumulation and status computation.
// Pure functions, no side effects.

import type { Usage } from "@earendil-works/pi-ai";
import type { TelemetryEvent, UsageAccumulator } from "./types.js";

/**
 * Create a fresh usage accumulator for a single deliberation.
 */
export function createUsageAccumulator(): UsageAccumulator {
  const usages: Usage[] = [];
  let successfulCalls = 0;

  return {
    get successfulCalls() {
      return successfulCalls;
    },
    get usages() {
      return usages.slice(); // defensive copy
    },

    addReported(usage: Usage): void {
      successfulCalls++;
      usages.push(usage);
    },

    addUnreported(): void {
      successfulCalls++;
    },

    compute(): { status: "not_applicable" | "unreported" | "partial" | "complete"; aggregate?: Usage } {
      if (successfulCalls === 0) {
        return { status: "not_applicable" };
      }
      const reportedCount = usages.length;
      if (reportedCount === 0) {
        return { status: "unreported" };
      }
      if (reportedCount < successfulCalls) {
        return { status: "partial" };
      }
      // reported === successful → complete, include aggregate
      return { status: "complete", aggregate: sumUsages(usages) };
    },
  };
}

/**
 * Sum an array of Usage objects.
 * Required fields are summed; optional fields (reasoning, cacheWrite1h) are
 * included only if at least one contribution defines them.
 */
function sumUsages(usages: Usage[]): Usage {
  let hasReasoning = false;
  let hasCacheWrite1h = false;

  const result: Usage = {
    input: 0,
    output: 0,
    cacheRead: 0,
    cacheWrite: 0,
    totalTokens: 0,
    cost: {
      input: 0,
      output: 0,
      cacheRead: 0,
      cacheWrite: 0,
      total: 0,
    },
  };

  for (const u of usages) {
    result.input += u.input;
    result.output += u.output;
    result.cacheRead += u.cacheRead;
    result.cacheWrite += u.cacheWrite;
    result.totalTokens += u.totalTokens;

    if (u.reasoning !== undefined) {
      hasReasoning = true;
      result.reasoning = (result.reasoning ?? 0) + u.reasoning;
    }
    if (u.cacheWrite1h !== undefined) {
      hasCacheWrite1h = true;
      result.cacheWrite1h = (result.cacheWrite1h ?? 0) + u.cacheWrite1h;
    }

    result.cost.input += u.cost.input;
    result.cost.output += u.cost.output;
    result.cost.cacheRead += u.cost.cacheRead;
    result.cost.cacheWrite += u.cost.cacheWrite;
    result.cost.total += u.cost.total;
  }

  // Remove optional fields if no contribution defined them
  if (!hasReasoning) delete (result as unknown as Record<string, unknown>).reasoning;
  if (!hasCacheWrite1h) delete (result as unknown as Record<string, unknown>).cacheWrite1h;

  return result;
}

/**
 * Build a deliberation_telemetry event.
 */
export function buildDeliberationTelemetry(
  baselineAvailable: boolean,
  baselineSupplied: boolean | undefined,
  acc: UsageAccumulator,
): TelemetryEvent {
  const baseline = baselineSupplied !== undefined ? baselineSupplied : "not_applicable";
  const { status, aggregate } = acc.compute();

  const event: TelemetryEvent = {
    type: "deliberation_telemetry" as const,
    baseline_available: baselineAvailable,
    baseline_supplied: baseline,
    successful_calls: acc.successfulCalls,
    reported_calls: acc.usages.length,
    usage_status: status,
  };

  if (aggregate) {
    event.aggregate_usage = aggregate;
  }

  return event;
}

/**
 * Safely invoke a telemetry callback; never throws.
 */
export function safeLog(callback: (event: TelemetryEvent) => void, event: TelemetryEvent): void {
  try {
    callback(event);
  } catch {
    // Telemetry failure must never affect deliberation.
  }
}