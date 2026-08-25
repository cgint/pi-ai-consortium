// pi-ai-consortium entrypoint
// Deliberation layer: multiple models probe before the agent answers.
//
// Architecture B: input starts async deliberation, context awaits & injects.

// Custom session entry type — persists deliberation in session JSONL
// so both user (session replay) and agent can see what guidance was given.
const CUSTOM_TYPE = "pi-ai-consortium";

import type {
  ExtensionAPI,
  ExtensionContext,
  InputEvent,
  ContextEvent,
  TurnStartEvent,
} from "@earendil-works/pi-coding-agent";
import type { AgentMessage } from "@earendil-works/pi-agent-core";
import { ConsortiumCore, getCurrentHumanUserTurn, type ModelCallFn } from "./src/core.js";
import { callModelWithAuth } from "./src/model.js";
import { DEFAULT_CONFIG, parseModelRef, reasoningSource } from "./src/config.js";
import { buildUserContext } from "./src/context.js";
import { ConsortiumLogger, createProgressCallback, formatVisibleMessage } from "./src/ui.js";
import type { ConsortiumConfig, TurnState, DeliberationResult, DeliberationModelInfo, GovernorMode, TelemetryEvent } from "./src/types.js";
import { createUsageAccumulator, buildDeliberationTelemetry, safeLog } from "./src/telemetry.js";
import { join, dirname } from "node:path";
import { readFile, writeFile, rename, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";

export default function (pi: ExtensionAPI): void {
  let enabled = true;
  let governorMode: GovernorMode = "smart_extractor";
  let maxTurnGap = 20;
  let periodicInterval = 10;
  let stateSupersessionGuard = false;
  let stateSupersessionGuardSource = "default";
  let turnsSinceLastAudit = 0;
  let pendingPeriodicUserInput = false;

  let turnState: TurnState = { deliberation: null };
  let lastExtractedContext: DeliberationResult["extractedContext"] | null = null;
  let logger: ConsortiumLogger | null = null;

  // Queue writes sequentially to prevent race conditions between rapid toggles.
  let persistPending: Promise<void> = Promise.resolve();

  async function persistSettings(
    cwd: string,
    opts: { enabled?: boolean; governorMode?: GovernorMode; maxTurnGap?: number; periodicInterval?: number; stateSupersessionGuard?: boolean },
  ): Promise<void> {
    persistPending = persistPending.then(async () => {
      try {
        const dir = join(cwd, ".pi");
        try {
          await mkdir(dir, { recursive: true });
        } catch {
          // Directory exists or mkdir failed.
        }
        const p = join(dir, "settings.json");
        const tmp = p + ".tmp";
        let s: Record<string, unknown> = {};
        if (existsSync(p)) {
          try {
            const raw = await readFile(p, "utf-8");
            s = JSON.parse(raw);
          } catch {
            // Corrupted file — overwrite.
          }
        }

        let existingConsortium: Record<string, unknown> = {};
        if (typeof s.consortium === "object" && s.consortium !== null) {
          existingConsortium = s.consortium as Record<string, unknown>;
        } else if (typeof s.consortium === "boolean") {
          existingConsortium = { enabled: s.consortium };
        }

        s.consortium = {
          enabled: opts.enabled !== undefined ? opts.enabled : (existingConsortium.enabled ?? enabled),
          governorMode: opts.governorMode !== undefined ? opts.governorMode : (existingConsortium.governorMode ?? governorMode),
          maxTurnGap: opts.maxTurnGap !== undefined ? opts.maxTurnGap : (existingConsortium.maxTurnGap ?? maxTurnGap),
          periodicInterval: opts.periodicInterval !== undefined ? opts.periodicInterval : (existingConsortium.periodicInterval ?? periodicInterval),
          stateSupersessionGuard: opts.stateSupersessionGuard !== undefined ? opts.stateSupersessionGuard : (existingConsortium.stateSupersessionGuard ?? stateSupersessionGuard),
        };

        await writeFile(tmp, JSON.stringify(s, null, 2) + "\n");
        await rename(tmp, p);
      } catch {
        // Best-effort persistence.
      }
    });
    await persistPending;
  }

  pi.on("session_start", async (_event, ctx) => {
    try {
      const p = join(ctx.cwd, ".pi", "settings.json");
      if (!existsSync(p)) return;
      const raw = await readFile(p, "utf-8");
      const s = JSON.parse(raw);
      if (typeof s.consortium === "boolean") {
        enabled = s.consortium;
      } else if (typeof s.consortium === "object" && s.consortium !== null) {
        if (s.consortium.enabled !== undefined) enabled = !!s.consortium.enabled;
        if (s.consortium.governorMode !== undefined) governorMode = s.consortium.governorMode as GovernorMode;
        if (typeof s.consortium.maxTurnGap === "number") maxTurnGap = s.consortium.maxTurnGap;
        if (typeof s.consortium.periodicInterval === "number") periodicInterval = s.consortium.periodicInterval;
        if (typeof s.consortium.stateSupersessionGuard === "boolean") {
          stateSupersessionGuard = s.consortium.stateSupersessionGuard;
          stateSupersessionGuardSource = "workspace_settings";
        }
      }
      if (!enabled && ctx.hasUI) {
        ctx.ui.setStatus("consortium", "consortium: disabled");
      }
    } catch {
      // Default to enabled — fail open for safety.
    }
  });

  pi.on("turn_start", (_event: TurnStartEvent) => {
    // Only reset if no in-flight deliberation (turn_start fires after input but before context)
    if (!turnState.deliberation) {
      turnState = { deliberation: null };
    }
  });

  pi.on("input", async (event: InputEvent, ctx: ExtensionContext) => {
    const userContext = buildUserContext(event, ctx);

    // Initialize logger once per session
    if (!logger) {
      logger = new ConsortiumLogger(ctx.cwd, ctx.sessionManager.getSessionId());
    }
    logger.log({ type: "turn_start", input: userContext });
    // The one new trigger: periodic mode audits immediately after user input.
    if (governorMode === "periodic") pendingPeriodicUserInput = true;

    return { action: "continue" };
  });

  // Before each LLM call, await deliberation and inject; periodic mode alone
  // adds an immediate audit after genuine user input.
  pi.on("context", async (event: ContextEvent, ctx: ExtensionContext) => {
    if (!enabled) {
      pendingPeriodicUserInput = false;
      if (ctx.hasUI) {
        ctx.ui.setStatus("consortium", "consortium: disabled");
      }
      return;
    }
    if (turnState.deliberation) {
      return;
    }

    if (event.messages.length === 0) {
      return;
    }

    // Only periodic mode gets the user-input trigger. All other modes retain
    // their original per-context path into the unchanged governor/C1-C4 flow.
    const periodicSchedule = governorMode === "periodic"
      ? schedulePeriodicAudit({ turnsSinceLastAudit, pendingPeriodicUserInput, periodicInterval })
      : undefined;
    if (periodicSchedule && !periodicSchedule.shouldRun) {
      turnsSinceLastAudit = periodicSchedule.nextTurnsSinceLastAudit;
      return;
    }

    if (periodicSchedule?.consumePendingPeriodicUserInput) {
      pendingPeriodicUserInput = false;
    }
    const turnsBeforeScheduledRun = turnsSinceLastAudit;
    if (periodicSchedule) {
      // A periodic audit selected by cadence or user input starts a fresh N-call interval.
      turnsSinceLastAudit = periodicSchedule.nextTurnsSinceLastAudit;
    }

    if (!logger) {
      logger = new ConsortiumLogger(ctx.cwd, ctx.sessionManager.getSessionId());
    }

    const onProgress = createProgressCallback(ctx);
    const runtimeConfig = {
      ...DEFAULT_CONFIG,
      governorMode,
      maxTurnGap,
      periodicInterval,
      stateSupersessionGuard,
    };

    logger.log({
      type: "governor_input",
      state_supersession_guard: stateSupersessionGuard,
      state_supersession_guard_source: stateSupersessionGuardSource,
      current_human_turn_length: getCurrentHumanUserTurn(event.messages).length,
    });

    turnState.deliberation = runDeliberation(
      runtimeConfig,
      event.messages,
      ctx,
      logger,
      onProgress,
      periodicSchedule?.governorTurnsSinceLastAudit ?? turnsSinceLastAudit,
      lastExtractedContext !== null,
    );

    try {
      const result = await turnState.deliberation;

      if (result.skippedByGovernor) {
        turnState.deliberation = null;
        lastExtractedContext = result.extractedContext ?? null;
        if (!periodicSchedule) turnsSinceLastAudit++;
        if (result.extractedContext) {
          logger?.logExtraction(result.extractedContext);
        }
        logger?.log({
          type: "injection_skipped",
          reason: result.governorReason || "SKIPPED_BY_GOVERNOR",
          probe_count: 0,
          extractedContext: result.extractedContext,
        });
        if (ctx.hasUI) {
          ctx.ui.setStatus("consortium", "consortium: ⏭ skipped");
          ctx.ui.notify(formatVisibleMessage(result), "info");
        }
        return;
      }

      // Periodic was reset when its audit was selected. Other modes retain
      // their original completion-based counter reset.
      if (!periodicSchedule) turnsSinceLastAudit = 0;

      if (result.synthesis.trim().startsWith("NO_CONTRIBUTION")) {
        turnState.deliberation = null;
        lastExtractedContext = result.extractedContext ?? null;
        if (result.extractedContext) {
          logger?.logExtraction(result.extractedContext);
        }
        logger?.log({
          type: "injection_skipped",
          reason: "NO_CONTRIBUTION",
          governor_reason: result.governorReason,
          probe_count: result.probes.length,
          probe_payload_chars: result.probePayloadChars,
          extractedContext: result.extractedContext,
        });
        if (ctx.hasUI) {
          ctx.ui.setStatus("consortium", "consortium: ✓ complete (nothing to add)");
          ctx.ui.notify(formatVisibleMessage(result), "info");
        }
        return;
      }

      const syntheticMessage: AgentMessage = {
        role: "user",
        content: `[CONSORTIUM DELIBERATION]\n\n${result.synthesis}`,
        timestamp: Date.now(),
      };

      const messages = [...event.messages];
      messages.push(syntheticMessage);
      turnState.deliberation = null;
      lastExtractedContext = result.extractedContext ?? null;
      if (result.extractedContext) {
        logger?.logExtraction(result.extractedContext);
      }

      logger?.log({
        type: "injection_complete",
        synthesis_length: result.synthesis.length,
        probe_count: result.probes.length,
        probe_payload_chars: result.probePayloadChars,
        errors: result.errors,
        governor_reason: result.governorReason,
        probes: result.probes,
        synthesis: result.synthesis,
        extractedContext: result.extractedContext,
      });

      // Persist in session JSONL
      try {
        pi.appendEntry(CUSTOM_TYPE, {
          schemaVersion: "0.1",
          kind: "deliberation",
          synthesis: result.synthesis,
          probe_count: result.probes.length,
          probe_payload_chars: result.probePayloadChars,
          extractedContext: result.extractedContext,
          errors: result.errors,
        });
      } catch {
        // Some modes don't support session append.
      }

      // Visible TUI notification
      if (ctx.hasUI) {
        ctx.ui.notify(formatVisibleMessage(result), result.errors?.length ? "warning" : "info");
      }

      if (result.errors) {
        if (ctx.hasUI) {
          ctx.ui.setStatus("consortium", `consortium: ⚠ ${result.errors.length} error(s)`);
        }
      } else {
        if (ctx.hasUI) {
          ctx.ui.setStatus("consortium", "consortium: ✓ complete");
        }
      }

      return { messages };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      logger?.log({ type: "deliberation_failed", error: msg });
      if (ctx.hasUI) {
        ctx.ui.setStatus("consortium", `consortium: ✖ failed: ${msg}`);
      }
      turnState.deliberation = null;
      turnsSinceLastAudit = turnsBeforeScheduledRun;
      return;
    }
  });

  pi.registerCommand("ai-consortium", {
    description: "Show consortium deliberation status and governor mode",
    handler: async (_args, ctx) => {
      const deliberationModel = resolveDeliberationModel(ctx);
      const info = [
        `Consortium: ${enabled ? "enabled" : "disabled"}`,
        `Deliberation Model: ${deliberationModel.provider}/${deliberationModel.id} (${deliberationModel.source})`,
        `Reasoning: ${DEFAULT_CONFIG.reasoning} (${reasoningSource})`,
        `Governor Mode: ${governorMode}`,
        `Max Turn Gap (Safety Net): ${maxTurnGap}`,
        `Periodic Interval: ${periodicInterval}`,
        `Turns Since Last Full Audit: ${turnsSinceLastAudit}`,
      ].join("\n");
      ctx.ui.notify(info, "info");
    },
  });

  pi.registerCommand("ai-consortium-on", {
    description: "Enable consortium deliberation",
    handler: async (_args, ctx) => {
      enabled = true;
      await persistSettings(ctx.cwd, { enabled: true });
      if (ctx.hasUI) {
        ctx.ui.setStatus("consortium", undefined);
      }
      ctx.ui.notify("Consortium enabled", "info");
    },
  });

  pi.registerCommand("ai-consortium-off", {
    description: "Disable consortium deliberation",
    handler: async (_args, ctx) => {
      enabled = false;
      await persistSettings(ctx.cwd, { enabled: false });
      if (ctx.hasUI) {
        ctx.ui.setStatus("consortium", "consortium: disabled");
      }
      ctx.ui.notify("Consortium disabled", "info");
    },
  });

  pi.registerCommand("ai-consortium-cadence", {
    description: "Set governor cadence mode: smart_extractor | always | periodic [N] | manual",
    handler: async (args, ctx) => {
      const parts = args.trim().split(/\s+/);
      const resolved = resolveCadenceMode(parts[0]?.toLowerCase() ?? "");

      if (!resolved.ok) {
        ctx.ui.notify(
          resolved.candidates.length > 1
            ? `Ambiguous prefix "${parts[0]}". Did you mean: ${resolved.candidates.join(" | ")}?`
            : "Usage: /ai-consortium-cadence <smart_extractor | always | periodic [N] | manual> (unambiguous prefix ok, e.g. p 5)",
          "warning",
        );
        return;
      }
      const mode = resolved.mode;

      governorMode = mode;
      if (governorMode !== "periodic") pendingPeriodicUserInput = false;
      let newInterval = periodicInterval;
      if (mode === "periodic" && parts[1] && !isNaN(parseInt(parts[1], 10))) {
        newInterval = parseInt(parts[1], 10);
        periodicInterval = newInterval;
      }

      await persistSettings(ctx.cwd, { governorMode, periodicInterval: newInterval });
      ctx.ui.notify(`Governor mode set to: ${governorMode}${governorMode === "periodic" ? ` (${periodicInterval} turns)` : ""}`, "info");
    },
  });

  pi.registerCommand("ai-consortium-context", {
    description: "Inspect the last turn's 9 extracted strategic context vectors",
    handler: async (_args, ctx) => {
      if (!lastExtractedContext) {
        ctx.ui.notify("No extracted context available yet for this session.", "info");
        return;
      }
      const fmt = (items?: string[]) => (!items || items.length === 0 ? "[none]" : items.join("; "));
      const summary = [
        `◇ Extracted 9 Strategic Context Vectors:`,
        `  • User Requirements: ${fmt(lastExtractedContext.userRequirements)}`,
        `  • Deliverables: ${fmt(lastExtractedContext.deliverables)}`,
        `  • Revised / Superseded: ${fmt(lastExtractedContext.revisedOrSupersededDirection)}`,
        `  • User Decisions: ${fmt(lastExtractedContext.userDecisions)}`,
        `  • Questions & Info Gaps: ${fmt(lastExtractedContext.questionsAndInformationGaps)}`,
        `  • Control Boundaries: ${fmt(lastExtractedContext.controlBoundaries)}`,
        `  • Observed Work: ${fmt(lastExtractedContext.observedWork)}`,
        `  • Observed Critical Facts: ${fmt(lastExtractedContext.observedCriticalFacts)}`,
        `  • Relevant Learnings: ${fmt(lastExtractedContext.relevantLearnings)}`,
      ].join("\n");

      ctx.ui.notify(summary, "info");
    },
  });
}

/** Resolve the deliberation model from CONSORTIUM_MODEL env var, falling back to ctx.model. */
function resolveDeliberationModel(
  ctx: ExtensionContext,
): { provider: string; id: string; source: string } {
  const ref = parseModelRef(process.env.CONSORTIUM_MODEL);
  if (ref) {
    const model = ctx.modelRegistry.find(ref.provider, ref.modelId);
    if (model) {
      return { provider: model.provider, id: model.id, source: "CONSORTIUM_MODEL" };
    }
    // Env var set but model not found — log warning and fall through
    console.warn(`[consortium] CONSORTIUM_MODEL="${process.env.CONSORTIUM_MODEL}" resolved but not found in model registry — falling back to executor model`);
  }
  // Fallback to executor model
  if (!ctx.model) {
    throw new Error("No active model available from ctx.model and CONSORTIUM_MODEL not resolvable");
  }
  return { provider: ctx.model.provider, id: ctx.model.id, source: "ctx.model" };
}

/** Run the full deliberation cycle. */
export async function runDeliberation(
  baseConfig: typeof DEFAULT_CONFIG,
  input: string | AgentMessage[],
  ctx: ExtensionContext,
  logger: ConsortiumLogger,
  onProgress: (phase: string, current: number, total: number, role?: string) => void,
  turnsSinceLastAudit: number,
  baselineAvailable: boolean,
): Promise<DeliberationResult> {
  const deliberationModel = resolveDeliberationModel(ctx);
  const modelRegistry = ctx.modelRegistry;

  const config: ConsortiumConfig = {
    ...baseConfig,
    probes: baseConfig.probes.map((p) => ({
      ...p,
      provider: deliberationModel.provider,
      modelId: deliberationModel.id,
    })),
    synthesis: {
      ...baseConfig.synthesis,
      provider: deliberationModel.provider,
      modelId: deliberationModel.id,
    },
    extraction: baseConfig.extraction
      ? {
          ...baseConfig.extraction,
          provider: deliberationModel.provider,
          modelId: deliberationModel.id,
        }
      : undefined,
  };

  logger.log({
    type: "deliberation_start",
    model: `${deliberationModel.provider}/${deliberationModel.id}`,
    modelSource: deliberationModel.source,
    probe_count: config.probes.length,
  });

  // ── Telemetry state (local to this runDeliberation call) ──
  const acc = createUsageAccumulator();
  let baselineSupplied: boolean | undefined;
  const telemetryLog = (event: TelemetryEvent): void => {
    logger.log(event);
  };

  const onBaselineCheck = (bs: boolean): void => {
    baselineSupplied = bs;
    safeLog(telemetryLog, { type: "baseline_check", baseline_available: baselineAvailable, baseline_supplied: bs });
  };

  const callModel: ModelCallFn = async (modelKey, system, user, _maxTokens, _temperature, signal, options) => {
    const start = Date.now();
    const { provider, modelId, role } = resolveModelKey(modelKey, config);

    logger.log({
      type: "probe_start",
      modelKey,
      role: role ?? undefined,
      provider,
      modelId,
      system_prompt: system,
      user_input: user,
    });

    try {
      const result = await callModelWithAuth(provider, modelId, system, user, modelRegistry, signal, undefined, config.reasoning, options);
      const duration = Date.now() - start;
      const usageReported = result.usage !== null;

      // Record usage in accumulator
      if (result.usage !== null) {
        acc.addReported(result.usage);
      } else {
        acc.addUnreported();
      }

      // Log probe_complete with usage_reported flag
      const logEntry: Record<string, unknown> = {
        type: "probe_complete",
        modelKey,
        role: role ?? undefined,
        duration_ms: duration,
        output_length: result.text.length,
        output: result.text,
        usage_reported: usageReported,
      };
      if (result.usage !== null) {
        logEntry.usage = result.usage;
      }
      logger.log(logEntry);

      return options?.tools?.length
        ? { text: result.text, ...(result.functionCalls ? { functionCalls: result.functionCalls } : {}) }
        : result.text;
    } catch (err) {
      const duration = Date.now() - start;
      const msg = err instanceof Error ? err.message : String(err);
      logger.log({ type: "probe_error", modelKey, duration_ms: duration, error: msg });
      throw err;
    }
  };

  const core = new ConsortiumCore(config, callModel, onBaselineCheck);
  const result = await core.deliberate(input, ctx.signal, onProgress, turnsSinceLastAudit);

  // ── Final deliberation_telemetry (after core completes) ──
  const finalEvent = buildDeliberationTelemetry(baselineAvailable, baselineSupplied, acc);
  safeLog(telemetryLog, finalEvent);

  const modelInfo: DeliberationModelInfo = {
    provider: deliberationModel.provider,
    modelId: deliberationModel.id,
    reasoning: config.reasoning,
    source: deliberationModel.source,
  };

  return { ...result, model: modelInfo };
}

export const CADENCE_MODES: GovernorMode[] = ["smart_extractor", "always", "periodic", "manual"];

export interface PeriodicAuditScheduleInput {
  turnsSinceLastAudit: number;
  pendingPeriodicUserInput: boolean;
  periodicInterval: number;
}

export interface PeriodicAuditSchedule {
  shouldRun: boolean;
  governorTurnsSinceLastAudit: number;
  nextTurnsSinceLastAudit: number;
  consumePendingPeriodicUserInput: boolean;
}

/**
 * The only user-input scheduling rule: in periodic mode, user input starts an
 * audit now and starts a fresh N-call interval. The effective count is an
 * adapter for the unchanged periodic governor; it does not change C1-C4.
 */
export function schedulePeriodicAudit(input: PeriodicAuditScheduleInput): PeriodicAuditSchedule {
  const { turnsSinceLastAudit, pendingPeriodicUserInput, periodicInterval } = input;
  const nextPeriodicCount = turnsSinceLastAudit + 1;
  const periodicCadenceIsDue = nextPeriodicCount >= periodicInterval;
  const periodicAuditShouldRun = pendingPeriodicUserInput || periodicCadenceIsDue;

  if (periodicAuditShouldRun) {
    return {
      shouldRun: true,
      governorTurnsSinceLastAudit: periodicInterval,
      nextTurnsSinceLastAudit: 0,
      consumePendingPeriodicUserInput: pendingPeriodicUserInput,
    };
  }

  return {
    shouldRun: false,
    governorTurnsSinceLastAudit: turnsSinceLastAudit,
    nextTurnsSinceLastAudit: nextPeriodicCount,
    consumePendingPeriodicUserInput: false,
  };
}

/** Resolve a (possibly abbreviated) cadence mode from unambiguous prefix matching. */
export function resolveCadenceMode(
  input: string,
  modes: GovernorMode[] = CADENCE_MODES,
): { ok: true; mode: GovernorMode } | { ok: false; candidates: GovernorMode[] } {
  const candidates = modes.filter((m) => m.startsWith(input));
  if (candidates.length === 0) return { ok: false, candidates: [] };
  if (candidates.length > 1) return { ok: false, candidates };
  return { ok: true, mode: candidates[0] };
}

/** Resolve provider + modelId from a modelKey string. */
function resolveModelKey(
  modelKey: string,
  config: ConsortiumConfig,
): { provider: string; modelId: string; role?: string } {
  if (modelKey === "synthesis") {
    return { provider: config.synthesis.provider, modelId: config.synthesis.modelId };
  }
  if (modelKey === "extraction") {
    if (config.extraction) {
      return { provider: config.extraction.provider, modelId: config.extraction.modelId };
    }
    return { provider: config.synthesis.provider, modelId: config.synthesis.modelId };
  }
  const match = modelKey.match(/^probe:(\d+)(?::(.+))?$/);
  if (match) {
    const i = parseInt(match[1], 10);
    const probe = config.probes[i];
    if (!probe) {
      throw new Error(`Probe ${i} not found in config`);
    }
    return { provider: probe.provider, modelId: probe.modelId, role: match[2] ?? probe.role };
  }
  throw new Error(`Unknown modelKey: "${modelKey}"`);
}