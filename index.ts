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
import type { ConsortiumConfig, TurnState, DeliberationResult } from "./src/types.js";
import { join, dirname } from "node:path";
import { readFile, writeFile, rename, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";

export default function (pi: ExtensionAPI): void {
  let enabled = true;
  let turnState: TurnState = { deliberation: null };
  let lastExtractedContext: DeliberationResult["extractedContext"] | null = null;
  let logger: ConsortiumLogger | null = null;

  // Queue writes sequentially to prevent race conditions between rapid toggles.
  let persistPending: Promise<void> = Promise.resolve();

  async function persistEnabled(cwd: string, value: boolean): Promise<void> {
    // Chain writes sequentially so they never race.
    persistPending = persistPending.then(async () => {
      try {
        const dir = join(cwd, ".pi");
        try {
          await mkdir(dir, { recursive: true });
        } catch {
          // Directory exists or mkdir failed — best effort.
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
        s.consortium = value;
        await writeFile(tmp, JSON.stringify(s, null, 2) + "\n");
        await rename(tmp, p); // Atomic on POSIX.
      } catch {
        // Best-effort persistence.
      }
    });
    // Wait for this write to complete so the command handler doesn't proceed
    // while a stale read is in flight.
    await persistPending;
  }

  pi.on("session_start", async (_event, ctx) => {
    try {
      const p = join(ctx.cwd, ".pi", "settings.json");
      if (!existsSync(p)) return;
      const raw = await readFile(p, "utf-8");
      const s = JSON.parse(raw);
      if (s.consortium !== undefined) {
        enabled = !!s.consortium;
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
    turnState.deliberation = runDeliberation(DEFAULT_CONFIG, event.messages, ctx, logger, onProgress);

    try {
      const result = await turnState.deliberation;

      if (result.synthesis.trim().startsWith("NO_CONTRIBUTION")) {
        turnState.deliberation = null;
        lastExtractedContext = result.extractedContext ?? null;
        logger?.log({
          type: "injection_skipped",
          reason: "NO_CONTRIBUTION",
          probe_count: result.probes.length,
          extractedContext: result.extractedContext,
        });
        ctx.ui.setStatus("consortium", "⏭ skipped (nothing to add)");
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
        ctx.ui.setStatus("consortium", `⚠ Deliberation had ${result.errors.length} error(s)`);
      } else {
        ctx.ui.setStatus("consortium", "✓ Deliberation complete");
      }

      return { messages };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      logger?.log({ type: "deliberation_failed", error: msg });
      ctx.ui.setStatus("consortium", `✖ Deliberation failed: ${msg}`);
      turnState.deliberation = null;
      return;
    }
  });

  pi.registerCommand("ai-consortium", {
    description: "Show consortium deliberation status (on/off)",
    handler: async (_args, ctx) => {
      ctx.ui.notify(`Consortium: ${enabled ? "enabled" : "disabled"}`, "info");
    },
  });

  pi.registerCommand("ai-consortium-on", {
    description: "Enable consortium deliberation",
    handler: async (_args, ctx) => {
      enabled = true;
      await persistEnabled(ctx.cwd, true);
      ctx.ui.notify("Consortium enabled", "info");
    },
  });

  pi.registerCommand("ai-consortium-off", {
    description: "Disable consortium deliberation",
    handler: async (_args, ctx) => {
      enabled = false;
      await persistEnabled(ctx.cwd, false);
      ctx.ui.notify("Consortium disabled", "info");
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
  return core.deliberate(input, ctx.signal, onProgress);
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