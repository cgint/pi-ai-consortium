import { describe, expect, it } from "vitest";
import { scheduleDeliberation } from "../index.js";

describe("scheduleDeliberation", () => {
  it("fires periodic cadence on the Nth LLM call and resets the counter", () => {
    const beforeDue = scheduleDeliberation({
      governorMode: "periodic",
      turnsSinceLastAudit: 9,
      pendingUserTurn: false,
      periodicInterval: 10,
      maxTurnGap: 20,
    });

    expect(beforeDue).toMatchObject({
      shouldRun: true,
      userInputTrigger: false,
      governorTurnsSinceLastAudit: 10,
      nextTurnsSinceLastAudit: 0,
      consumePendingUserTurn: false,
    });
  });

  it("fires and resets early for user input without consuming the next periodic cadence", () => {
    const input = scheduleDeliberation({
      governorMode: "periodic",
      turnsSinceLastAudit: 5,
      pendingUserTurn: true,
      periodicInterval: 10,
      maxTurnGap: 20,
    });

    expect(input).toMatchObject({
      shouldRun: true,
      userInputTrigger: true,
      governorTurnsSinceLastAudit: 10,
      nextTurnsSinceLastAudit: 0,
      consumePendingUserTurn: true,
    });

    const firstSubsequentCall = scheduleDeliberation({
      governorMode: "periodic",
      turnsSinceLastAudit: input.nextTurnsSinceLastAudit,
      pendingUserTurn: false,
      periodicInterval: 10,
      maxTurnGap: 20,
    });
    expect(firstSubsequentCall).toMatchObject({
      shouldRun: false,
      nextTurnsSinceLastAudit: 1,
    });
  });

  it("dispatches smart_extractor on user input without forcing its C2 decision", () => {
    const decision = scheduleDeliberation({
      governorMode: "smart_extractor",
      turnsSinceLastAudit: 5,
      pendingUserTurn: true,
      periodicInterval: 10,
      maxTurnGap: 20,
    });

    expect(decision).toMatchObject({
      shouldRun: true,
      userInputTrigger: true,
      governorTurnsSinceLastAudit: 6,
      nextTurnsSinceLastAudit: 0,
      consumePendingUserTurn: true,
    });
  });

  it("does not auto-trigger or retain stale input in manual mode", () => {
    const decision = scheduleDeliberation({
      governorMode: "manual",
      turnsSinceLastAudit: 5,
      pendingUserTurn: true,
      periodicInterval: 10,
      maxTurnGap: 20,
    });

    expect(decision).toMatchObject({
      shouldRun: false,
      nextTurnsSinceLastAudit: 5,
      consumePendingUserTurn: true,
    });
  });
});
