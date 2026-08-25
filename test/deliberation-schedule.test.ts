import { describe, expect, it } from "vitest";
import { schedulePeriodicAudit } from "../index.js";

describe("schedulePeriodicAudit", () => {
  it("fires on the Nth LLM call and resets the periodic counter", () => {
    const schedule = schedulePeriodicAudit({
      turnsSinceLastAudit: 9,
      pendingPeriodicUserInput: false,
      periodicInterval: 10,
    });

    expect(schedule).toEqual({
      shouldRun: true,
      governorTurnsSinceLastAudit: 10,
      nextTurnsSinceLastAudit: 0,
      consumePendingPeriodicUserInput: false,
    });
  });

  it("fires immediately for user input and resets the periodic counter", () => {
    const schedule = schedulePeriodicAudit({
      turnsSinceLastAudit: 5,
      pendingPeriodicUserInput: true,
      periodicInterval: 10,
    });

    expect(schedule).toEqual({
      shouldRun: true,
      governorTurnsSinceLastAudit: 10,
      nextTurnsSinceLastAudit: 0,
      consumePendingPeriodicUserInput: true,
    });
  });

  it("starts counting a fresh N-call interval after a user-input audit", () => {
    const schedule = schedulePeriodicAudit({
      turnsSinceLastAudit: 0,
      pendingPeriodicUserInput: false,
      periodicInterval: 10,
    });

    expect(schedule).toEqual({
      shouldRun: false,
      governorTurnsSinceLastAudit: 0,
      nextTurnsSinceLastAudit: 1,
      consumePendingPeriodicUserInput: false,
    });
  });
});
