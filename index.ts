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

export default function (pi: ExtensionAPI): void {
  let turnState: TurnState = { deliberation: null };
  let logger: ConsortiumLogger | null = null;

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
    turnState.deliberation = runDeliberation(DEFAULT_CONFIG, userContext, ctx, logger, onProgress);

    try {
      const result = await turnState.deliberation;

      if (result.synthesis.trim().startsWith("NO_CONTRIBUTION")) {
        turnState.deliberation = null;
        logger?.log({
          type: "injection_skipped",
          reason: "NO_CONTRIBUTION",
          probe_count: result.probes.length,
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

      logger?.log({
        type: "injection_complete",
        synthesis_length: result.synthesis.length,
        probe_count: result.probes.length,
        errors: result.errors,
        probes: result.probes,
        synthesis: result.synthesis,
      });

      // Persist in session JSONL
      try {
        pi.appendEntry(CUSTOM_TYPE, {
          schemaVersion: "0.1",
          kind: "deliberation",
          synthesis: result.synthesis,
          probe_count: result.probes.length,
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
}

/** Run the full deliberation cycle. */
async function runDeliberation(
  baseConfig: typeof DEFAULT_CONFIG,
  userContext: string,
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
  return core.deliberate(userContext, ctx.signal, onProgress);
}

/** Resolve provider + modelId from a modelKey string. */
function resolveModelKey(
  modelKey: string,
  config: ConsortiumConfig,
): { provider: string; modelId: string } {
  if (modelKey === "synthesis") {
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