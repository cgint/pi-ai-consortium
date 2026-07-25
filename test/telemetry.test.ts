// Telemetry accumulator tests — usage accumulation, status computation, and aggregation.

import { describe, expect, it } from "vitest";
import { createUsageAccumulator, buildDeliberationTelemetry, safeLog } from "../src/telemetry.js";
import type { Usage } from "@earendil-works/pi-ai";

function makeUsage(overrides: Partial<Usage> = {}): Usage {
  return {
    input: 10,
    output: 20,
    cacheRead: 0,
    cacheWrite: 0,
    totalTokens: 30,
    cost: { input: 0.1, output: 0.2, cacheRead: 0, cacheWrite: 0, total: 0.3 },
    ...overrides,
  };
}

// ── Accumulator status tests ──

describe("UsageAccumulator.status", () => {
  it("0 successful → not_applicable, no aggregate", () => {
    const acc = createUsageAccumulator();
    const result = acc.compute();
    expect(result.status).toBe("not_applicable");
    expect(result.aggregate).toBeUndefined();
  });

  it("successful > 0 and 0 reported → unreported, no aggregate", () => {
    const acc = createUsageAccumulator();
    acc.addUnreported();
    acc.addUnreported();
    const result = acc.compute();
    expect(result.status).toBe("unreported");
    expect(result.aggregate).toBeUndefined();
    expect(acc.successfulCalls).toBe(2);
  });

  it("0 < reported < successful → partial, no aggregate", () => {
    const acc = createUsageAccumulator();
    acc.addReported(makeUsage({ input: 10, output: 20 }));
    acc.addUnreported();
    acc.addReported(makeUsage({ input: 5, output: 10 }));
    const result = acc.compute();
    expect(result.status).toBe("partial");
    expect(result.aggregate).toBeUndefined();
    expect(acc.successfulCalls).toBe(3);
  });

  it("reported === successful → complete, include aggregate", () => {
    const acc = createUsageAccumulator();
    acc.addReported(makeUsage({ input: 10, output: 20, totalTokens: 30, cost: { input: 0.1, output: 0.2, cacheRead: 0, cacheWrite: 0, total: 0.3 } }));
    acc.addReported(makeUsage({ input: 5, output: 15, totalTokens: 20, cost: { input: 0.05, output: 0.15, cacheRead: 0, cacheWrite: 0, total: 0.2 } }));
    const result = acc.compute();
    expect(result.status).toBe("complete");
    expect(result.aggregate).toBeDefined();
    expect(result.aggregate!.input).toBe(15);
    expect(result.aggregate!.output).toBe(35);
    expect(result.aggregate!.totalTokens).toBe(50);
    expect(result.aggregate!.cost.total).toBe(0.5);
  });
});

// ── Aggregate field summation ──

describe("UsageAccumulator.aggregate fields", () => {
  it("sums all required numeric and cost fields", () => {
    const acc = createUsageAccumulator();
    acc.addReported(makeUsage({ input: 100, output: 50, cacheRead: 10, cacheWrite: 5, totalTokens: 165, cost: { input: 1, output: 2, cacheRead: 0.1, cacheWrite: 0.2, total: 3.3 } }));
    acc.addReported(makeUsage({ input: 200, output: 100, cacheRead: 20, cacheWrite: 10, totalTokens: 330, cost: { input: 2, output: 4, cacheRead: 0.2, cacheWrite: 0.4, total: 6.6 } }));
    const { aggregate } = acc.compute();
    expect(aggregate).toMatchObject({
      input: 300,
      output: 150,
      cacheRead: 30,
      cacheWrite: 15,
      totalTokens: 495,
    });
    // Floating-point cost fields — approximate match
    expect(aggregate.cost.input).toBeCloseTo(3, 9);
    expect(aggregate.cost.output).toBeCloseTo(6, 9);
    expect(aggregate.cost.cacheRead).toBeCloseTo(0.3, 9);
    expect(aggregate.cost.cacheWrite).toBeCloseTo(0.6, 9);
    expect(aggregate.cost.total).toBeCloseTo(9.9, 9);
  });

  it("includes optional reasoning only if at least one contribution defines it", () => {
    const acc = createUsageAccumulator();
    acc.addReported(makeUsage({ input: 10, output: 20, reasoning: 15 }));
    acc.addReported(makeUsage({ input: 5, output: 10 })); // no reasoning
    const { aggregate } = acc.compute();
    expect(aggregate!.reasoning).toBe(15);
  });

  it("omits optional reasoning when no contribution defines it", () => {
    const acc = createUsageAccumulator();
    acc.addReported(makeUsage({ input: 10, output: 20 }));
    acc.addReported(makeUsage({ input: 5, output: 10 }));
    const { aggregate } = acc.compute();
    expect((aggregate! as Record<string, unknown>).reasoning).toBeUndefined();
  });

  it("includes optional cacheWrite1h only if at least one contribution defines it", () => {
    const acc = createUsageAccumulator();
    acc.addReported(makeUsage({ input: 10, output: 20, cacheWrite1h: 3 }));
    acc.addReported(makeUsage({ input: 5, output: 10 }));
    const { aggregate } = acc.compute();
    expect(aggregate!.cacheWrite1h).toBe(3);
  });

  it("omits optional cacheWrite1h when no contribution defines it", () => {
    const acc = createUsageAccumulator();
    acc.addReported(makeUsage({ input: 10, output: 20 }));
    acc.addReported(makeUsage({ input: 5, output: 10 }));
    const { aggregate } = acc.compute();
    expect((aggregate! as Record<string, unknown>).cacheWrite1h).toBeUndefined();
  });
});

// ── buildDeliberationTelemetry ──

describe("buildDeliberationTelemetry", () => {
  it("emits not_applicable when no calls", () => {
    const acc = createUsageAccumulator();
    const event = buildDeliberationTelemetry(false, undefined, acc);
    expect(event.type).toBe("deliberation_telemetry");
    expect(event.baseline_available).toBe(false);
    expect(event.baseline_supplied).toBe("not_applicable");
    expect(event.successful_calls).toBe(0);
    expect(event.reported_calls).toBe(0);
    expect(event.usage_status).toBe("not_applicable");
    expect(event.aggregate_usage).toBeUndefined();
  });

  it("emits baseline_available:false, baseline_supplied:false for first attempt", () => {
    const acc = createUsageAccumulator();
    acc.addReported(makeUsage());
    const event = buildDeliberationTelemetry(false, false, acc);
    expect(event.baseline_available).toBe(false);
    expect(event.baseline_supplied).toBe(false);
  });

  it("emits baseline_available:true, baseline_supplied:true for later attempt with carry", () => {
    const acc = createUsageAccumulator();
    acc.addReported(makeUsage());
    const event = buildDeliberationTelemetry(true, true, acc);
    expect(event.baseline_available).toBe(true);
    expect(event.baseline_supplied).toBe(true);
  });

  it("includes aggregate_usage only when status is complete", () => {
    const acc = createUsageAccumulator();
    acc.addReported(makeUsage());
    const event = buildDeliberationTelemetry(true, true, acc);
    expect(event.usage_status).toBe("complete");
    expect(event.aggregate_usage).toBeDefined();
  });

  it("omits aggregate_usage when status is partial", () => {
    const acc = createUsageAccumulator();
    acc.addReported(makeUsage());
    acc.addUnreported();
    const event = buildDeliberationTelemetry(true, true, acc);
    expect(event.usage_status).toBe("partial");
    expect(event.aggregate_usage).toBeUndefined();
  });

  it("omits aggregate_usage when status is unreported", () => {
    const acc = createUsageAccumulator();
    acc.addUnreported();
    const event = buildDeliberationTelemetry(true, true, acc);
    expect(event.usage_status).toBe("unreported");
    expect(event.aggregate_usage).toBeUndefined();
  });
});

// ── safeLog ──

describe("safeLog", () => {
  it("invokes callback with event", () => {
    const events: any[] = [];
    const cb = (e: any) => events.push(e);
    safeLog(cb, { type: "baseline_check", baseline_available: true, baseline_supplied: true });
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("baseline_check");
  });

  it("swallows callback exceptions", () => {
    const cb = () => { throw new Error("boom"); };
    expect(() => safeLog(cb, { type: "baseline_check", baseline_available: true, baseline_supplied: true })).not.toThrow();
  });
});