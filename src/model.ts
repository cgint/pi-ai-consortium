/**
 * Model invocation with auth forwarding.
 *
 * Replaces the createAgentSession approach that failed to inherit auth.
 * Follows the pattern from pi-advisor and pi-self-reflect:
 *   1. modelRegistry.find(provider, modelId)
 *   2. modelRegistry.getApiKeyAndHeaders(model)
 *   3. complete(model, context, { apiKey, headers, signal })
 */

import { streamSimple } from "@earendil-works/pi-ai/compat";
import type { Context, Usage, ThinkingLevel } from "@earendil-works/pi-ai";
import type { ModelCallOptions } from "./core.js";

/**
 * Minimal model registry interface matching pi-coding-agent's ModelRegistry.
 * We keep this loose to avoid a dependency on pi-coding-agent's internal types.
 */
export interface ModelRegistry {
  find(provider: string, modelId: string): { provider: string; id: string; apiKey?: string } | undefined;
  getApiKeyAndHeaders(model: { provider: string; id: string }): Promise<{
    ok: boolean;
    apiKey?: string;
    headers?: Record<string, string | null>;
    error?: string;
  }>;
  getApiKeyForProvider?(provider: string): Promise<string | undefined>;
}

/** Extract text content from an AssistantMessage. */
function functionCallsFromMessage(msg: { content: unknown }): Array<{ id: string; name: string; arguments: Record<string, unknown> }> {
  if (!Array.isArray(msg.content)) return [];
  return msg.content
    .filter(
      (part): part is { type: "toolCall"; id: string; name: string; arguments: Record<string, unknown> } =>
        Boolean(part) &&
        typeof part === "object" &&
        (part as { type?: unknown }).type === "toolCall" &&
        typeof (part as { id?: unknown }).id === "string" &&
        typeof (part as { name?: unknown }).name === "string" &&
        typeof (part as { arguments?: unknown }).arguments === "object" &&
        (part as { arguments?: unknown }).arguments !== null,
    )
    .map((part) => ({ id: part.id, name: part.name, arguments: part.arguments }));
}

function textFromMessage(msg: { content: unknown }): string {
  if (typeof msg.content === "string") return msg.content.trim();
  if (!Array.isArray(msg.content)) return "";
  return msg.content
    .filter(
      (part): part is { type: "text"; text: string } =>
        Boolean(part) &&
        typeof part === "object" &&
        (part as { type?: unknown }).type === "text" &&
        typeof (part as { text?: unknown }).text === "string",
    )
    .map((part) => part.text)
    .join("\n")
    .trim();
}

/**
 * Call a model with auth forwarded from the parent context.
 * Returns `{ text, usage }` where `usage` is the Pi `Usage` when `totalTokens > 0`,
 * otherwise `null` (all-zero means unreported).
 * Throws on: model not found, auth failure, model call errors.
 */
export interface CallModelResult {
  text: string;
  functionCalls?: readonly { id: string; name: string; arguments: Record<string, unknown> }[];
  usage: Usage | null;
}

const RETRY_DELAY_MS = 500;
const DEFAULT_RETRIES = 1;

export async function callModelWithAuth(
  provider: string,
  modelId: string,
  systemPrompt: string,
  userPrompt: string,
  modelRegistry: ModelRegistry,
  signal?: AbortSignal,
  retries: number = DEFAULT_RETRIES,
  reasoning?: ThinkingLevel,
  options?: ModelCallOptions,
): Promise<CallModelResult> {
  const model = modelRegistry.find(provider, modelId);
  if (!model) {
    throw new Error(`Model not found: ${provider}/${modelId}`);
  }

  const auth = await modelRegistry.getApiKeyAndHeaders(model);
  if (!auth.ok) {
    throw new Error(auth.error ?? "Unknown auth error");
  }

  let apiKey = auth.apiKey;

  if (!apiKey) {
    // Some providers declare no-api-key-needed. Try provider-level resolution
    // as a fallback, then check the model's raw apiKey field.
    const fallbackKey = await modelRegistry.getApiKeyForProvider?.(provider);
    if (fallbackKey) {
      apiKey = fallbackKey;
    } else if (model.apiKey === "none" || model.apiKey === "no-api-key-needed") {
      apiKey = model.apiKey;
    }
  }

  if (!apiKey) {
    throw new Error(`No API key available for ${provider}/${modelId}.`);
  }

  const context: Context = {
    systemPrompt,
    messages: [
      {
        role: "user",
        content: [{ type: "text" as const, text: userPrompt }],
        timestamp: Date.now(),
      },
    ],
    tools: options?.tools as Context["tools"],
  };

  let lastError: Error | undefined;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      // Re-invoke streamSimple per attempt — a settled stream cannot be re-read.
      const eventStream = streamSimple(model as any, context, {
        apiKey,
        headers: auth.headers,
        signal,
        ...(reasoning ? { reasoning } : {}),
      } as any);

      const result = await eventStream.result();

      // Loud boundary 1: provider said the call errored or was aborted.
      // pi-ai's result() RESOLVES (does not reject) on error events, so
      // without this check the empty text silently becomes NO_CONTRIBUTION.
      if (result.stopReason === "error" || result.stopReason === "aborted") {
        throw new Error(
          result.errorMessage ?? `Model call stopped: ${result.stopReason}`,
        );
      }

      // Extract text from the AssistantMessage response
      const text = textFromMessage(result);
      const functionCalls = functionCallsFromMessage(result);

      // Loud boundary 2: no usable content at all — provider anomaly.
      // Structured extraction is valid with a tool call and no text response.
      if (text.length === 0 && functionCalls.length === 0) {
        throw new Error(
          `Empty response from ${provider}/${modelId} ` +
          `(stopReason=${result.stopReason}, totalTokens=${result.usage?.totalTokens ?? 0})`,
        );
      }

      // Retain usage if totalTokens > 0; all-zero means unreported → null
      const usage = result.usage && result.usage.totalTokens > 0 ? result.usage : null;
      return { text, ...(functionCalls.length > 0 ? { functionCalls } : {}), usage };
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      if (attempt >= retries || signal?.aborted) throw lastError;
      await new Promise((r) => setTimeout(r, RETRY_DELAY_MS));
    }
  }
  throw lastError;
}
