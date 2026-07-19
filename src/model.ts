/**
 * Model invocation with auth forwarding.
 *
 * Replaces the createAgentSession approach that failed to inherit auth.
 * Follows the pattern from pi-advisor and pi-self-reflect:
 *   1. modelRegistry.find(provider, modelId)
 *   2. modelRegistry.getApiKeyAndHeaders(model)
 *   3. complete(model, context, { apiKey, headers, signal })
 */

import { complete } from "@earendil-works/pi-ai";
import type { Context } from "@earendil-works/pi-ai";

/**
 * Minimal model registry interface matching pi-coding-agent's ModelRegistry.
 * We keep this loose to avoid a dependency on pi-coding-agent's internal types.
 */
export interface ModelRegistry {
  find(provider: string, modelId: string): { provider: string; id: string; apiKey?: string } | undefined;
  getApiKeyAndHeaders(model: { provider: string; id: string }): Promise<{
    ok: boolean;
    apiKey?: string;
    headers?: Record<string, string>;
    error?: string;
  }>;
  getApiKeyForProvider?(provider: string): Promise<string | undefined>;
}

/** Extract text content from an AssistantMessage. */
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
 * Throws on: model not found, auth failure, model call errors.
 */
export async function callModelWithAuth(
  provider: string,
  modelId: string,
  systemPrompt: string,
  userPrompt: string,
  modelRegistry: ModelRegistry,
  signal?: AbortSignal,
): Promise<string> {
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
    tools: [],
  };

  const result = await complete(model as any, context, {
    apiKey,
    headers: auth.headers,
    signal,
  } as any);

  // Extract text from the AssistantMessage response
  return textFromMessage(result);
}
