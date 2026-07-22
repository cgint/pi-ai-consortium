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
import { ConsortiumCore, type ModelCallFn } from "./src/core.js";
import { callModelWithAuth } from "./src/model.js";
import { DEFAULT_CONFIG } from "./src/config.js";
import { buildUserContext, buildUserContextFromMessages } from "./src/context.js";
import { ConsortiumLogger, createProgressCallback, formatVisibleMessage } from "./src/ui.js";
import type { ConsortiumConfig, TurnState, DeliberationResult, GovernorMode } from "./src/types.js";
import { join, dirname } from "node:path";
import { readFile, writeFile, rename, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";

export default function (pi: ExtensionAPI): void {
  let enabled = true;
  let governorMode: GovernorMode = "smart_extractor";
  let maxTurnGap = 20;
  let periodicInterval = 3;
  let turnsSinceLastAudit = 0;

  let turnState: TurnState = { deliberation: null };
  let lastExtractedContext: DeliberationResult["extractedContext"] | null = null;
  let logger: ConsortiumLogger | null = null;

  // Queue writes sequentially to prevent race conditions between rapid toggles.
  let persistPending: Promise<void> = Promise.resolve();

  async function persistSettings(
    cwd: string,
    opts: { enabled?: boolean; governorMode?: GovernorMode; maxTurnGap?: number; periodicInterval?: number },
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

    return { action: "continue" };
  });

  // On first LLM call of the turn, await deliberation and inject.
  pi.on("context", async (event: ContextEvent, ctx: ExtensionContext) => {
    if (!enabled) {
      if (ctx.hasUI) {
        ctx.ui.setStatus("consortium", "consortium: disabled");
      }
      return;
    }
    if (turnState.deliberation) {
      return;
    }

    const userContext = buildUserContextFromMessages(event.messages);
    if (!userContext) {
      return;
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
    };

    turnState.deliberation = runDeliberation(runtimeConfig, event.messages, ctx, logger, onProgress, turnsSinceLastAudit);

    try {
      const result = await turnState.deliberation;

      if (result.skippedByGovernor) {
        turnState.deliberation = null;
        lastExtractedContext = result.extractedContext ?? null;
        turnsSinceLastAudit++;
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

      // Full probe audit ran — reset turn counter gap
      turnsSinceLastAudit = 0;

      if (result.synthesis.trim().startsWith("NO_CONTRIBUTION")) {
        turnState.deliberation = null;
        lastExtractedContext = result.extractedContext ?? null;
        if (result.extractedContext) {
          logger?.logExtraction(result.extractedContext);
        }
        logger?.log({
          type: "injection_skipped",
          reason: "NO_CONTRIBUTION",
          probe_count: result.probes.length,
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
        errors: result.errors,
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
      return;
    }
  });

  pi.registerCommand("ai-consortium", {
    description: "Show consortium deliberation status and governor mode",
    handler: async (_args, ctx) => {
      const info = [
        `Consortium: ${enabled ? "enabled" : "disabled"}`,
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
      const mode = parts[0]?.toLowerCase() as GovernorMode | undefined;

      if (!mode || !["smart_extractor", "always", "periodic", "manual"].includes(mode)) {
        ctx.ui.notify("Usage: /ai-consortium-cadence <smart_extractor | always | periodic [N] | manual>", "warning");
        return;
      }

      governorMode = mode;
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
    description: "Inspect the last turn's 5 extracted context vectors",
    handler: async (_args, ctx) => {
      if (!lastExtractedContext) {
        ctx.ui.notify("No extracted context available yet for this session.", "info");
        return;
      }
      const summary = [
        `◇ Extracted Context Vectors:`,
        `  • Intent & Motive: ${lastExtractedContext.userIntentAndMotive}`,
        `  • Constraints & Guards: ${lastExtractedContext.activeConstraintsAndGuards}`,
        `  • Verified Facts: ${lastExtractedContext.verifiedFactsInventory}`,
        `  • Evidence Freshness: ${lastExtractedContext.evidenceFreshnessDelta}`,
        `  • Clarity Score: ${lastExtractedContext.clarityAndAmbiguityScore}${lastExtractedContext.missingDetails ? ` (${lastExtractedContext.missingDetails})` : ""}`,
      ].join("\n");

      ctx.ui.notify(summary, "info");
    },
  });
}

/** Run the full deliberation cycle. */
async function runDeliberation(
  baseConfig: typeof DEFAULT_CONFIG,
  input: string | AgentMessage[],
  ctx: ExtensionContext,
  logger: ConsortiumLogger,
  onProgress?: (phase: string, current: number, total: number, role?: string) => void,
  turnsSinceLastAudit: number = 0,
): Promise<DeliberationResult> {
  const activeModel = ctx.model;
  if (!activeModel) {
    throw new Error("No active model available from ctx.model");
  }

  const modelRegistry = ctx.modelRegistry;

  const config: ConsortiumConfig = {
    ...baseConfig,
    probes: baseConfig.probes.map((p) => ({
      ...p,
      provider: activeModel.provider,
      modelId: activeModel.id,
    })),
    synthesis: {
      ...baseConfig.synthesis,
      provider: activeModel.provider,
      modelId: activeModel.id,
    },
    extraction: baseConfig.extraction
      ? {
          ...baseConfig.extraction,
          provider: activeModel.provider,
          modelId: activeModel.id,
        }
      : undefined,
  };

  logger.log({
    type: "deliberation_start",
    model: `${activeModel.provider}/${activeModel.id}`,
    probe_count: config.probes.length,
  });

  const callModel: ModelCallFn = async (modelKey, system, user, _maxTokens, _temperature, signal) => {
    const start = Date.now();
    const { provider, modelId } = resolveModelKey(modelKey, config);

    logger.log({
      type: "probe_start",
      modelKey,
      provider,
      modelId,
      system_prompt: system,
      user_input: user,
    });

    try {
      const result = await callModelWithAuth(provider, modelId, system, user, modelRegistry, signal);
      const duration = Date.now() - start;
      logger.log({ type: "probe_complete", modelKey, duration_ms: duration, output_length: result.length, output: result });
      return result;
    } catch (err) {
      const duration = Date.now() - start;
      const msg = err instanceof Error ? err.message : String(err);
      logger.log({ type: "probe_error", modelKey, duration_ms: duration, error: msg });
      throw err;
    }
  };

  const core = new ConsortiumCore(config, callModel);
  return core.deliberate(input, ctx.signal, onProgress, turnsSinceLastAudit);
}

/** Resolve provider + modelId from a modelKey string. */
function resolveModelKey(
  modelKey: string,
  config: ConsortiumConfig,
): { provider: string; modelId: string } {
  if (modelKey === "synthesis") {
    return { provider: config.synthesis.provider, modelId: config.synthesis.modelId };
  }
  if (modelKey === "extraction") {
    if (config.extraction) {
      return { provider: config.extraction.provider, modelId: config.extraction.modelId };
    }
    return { provider: config.synthesis.provider, modelId: config.synthesis.modelId };
  }
  const match = modelKey.match(/^probe:(\d+)$/);
  if (match) {
    const i = parseInt(match[1], 10);
    const probe = config.probes[i];
    if (!probe) {
      throw new Error(`Probe ${i} not found in config`);
    }
    return { provider: probe.provider, modelId: probe.modelId };
  }
  throw new Error(`Unknown modelKey: "${modelKey}"`);
}