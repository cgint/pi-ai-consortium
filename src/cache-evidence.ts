// Cache-evidence helpers — fingerprint the Pi model context without retaining prompt content.
//
// These fingerprints establish request-prefix parity at the Pi streamSimple boundary.
// They do not claim that a provider used a cache entry or identify a cache source.

import { createHash } from "node:crypto";
import type { ModelCallOptions } from "./core.js";

const HISTORY_END = "</historical_observed_past>";

export interface CacheRequestFingerprint {
  /** SHA-256 of the canonical Pi context through the complete observed-history block. */
  prefixSha256?: string;
  /** UTF-8 byte length of that prefix; omitted when no complete history block exists. */
  prefixBytes?: number;
  /** SHA-256 of the complete canonical Pi context. */
  requestSha256: string;
  /** UTF-8 byte length of the complete canonical Pi context. */
  requestBytes: number;
  /** Whether the user payload contains a complete observed-history block. */
  historyComplete: boolean;
}

/** Deterministically serialize JSON-compatible data without retaining it in telemetry. */
function stableJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  const object = value as Record<string, unknown>;
  return `{${Object.keys(object).sort().map((key) => `${JSON.stringify(key)}:${stableJson(object[key])}`).join(",")}}`;
}

function sha256(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function byteLength(value: string): number {
  return Buffer.byteLength(value, "utf8");
}

function requestEnvelope(system: string, user: string, options?: ModelCallOptions): Record<string, unknown> {
  return {
    system,
    messages: [{ role: "user", content: user }],
    tools: options?.tools ?? [],
  };
}

/**
 * Fingerprint the exact Pi Context inputs supplied to streamSimple.
 *
 * The prefix includes system text and tool declarations because both are part of
 * the Pi context before the user history. A matching `prefixSha256` is therefore
 * necessary evidence for C1/C3 prefix parity at this boundary, not evidence that
 * the provider reused a cache entry.
 */
export function fingerprintCacheRequest(
  system: string,
  user: string,
  options?: ModelCallOptions,
): CacheRequestFingerprint {
  const fullEnvelope = requestEnvelope(system, user, options);
  const completeHistoryEnd = user.indexOf(HISTORY_END);
  const historyComplete = completeHistoryEnd >= 0;
  const historyUserPrefix = historyComplete
    ? user.slice(0, completeHistoryEnd + HISTORY_END.length)
    : undefined;

  const request = stableJson(fullEnvelope);
  const prefix = historyUserPrefix === undefined
    ? undefined
    : stableJson(requestEnvelope(system, historyUserPrefix, options));

  return {
    ...(prefix === undefined ? {} : { prefixSha256: sha256(prefix), prefixBytes: byteLength(prefix) }),
    requestSha256: sha256(request),
    requestBytes: byteLength(request),
    historyComplete,
  };
}
