// Consortium types — pure interfaces, no runtime dependencies.

/** High-level strategic context vectors extracted from session history. */
export interface ExtractedContext {
  /** 1. Macro goals, technical criteria, and quality expectations set by user. */
  userRequirements: string[];
  /** 2. Explicit required architectural artifacts, files, or reports expected. */
  deliverables: string[];
  /** 3. Directions, goals, or constraints that were canceled, updated, or superseded. */
  revisedOrSupersededDirection: string[];
  /** 4. Confirmed user decisions, approved trade-offs, and design preferences. */
  userDecisions: string[];
  /** 5. High-level domain ambiguities or unaddressed user questions requiring clarification. */
  questionsAndInformationGaps: string[];
  /** 6. Active session rules, allowed path boundaries, and mode flags. */
  controlBoundaries: string[];
  /** 7. Verified milestone progress achieved so far (high-level, not individual tool calls). */
  observedWork: string[];
  /** 8. Verified domain truths, system behaviors, and test outcomes observed in logs. */
  observedCriticalFacts: string[];
  /** 9. Systemic insights, structural architecture patterns, or project rules learned. */
  relevantLearnings: string[];
  /** Signal from context extraction pass whether full probe deliberation is recommended. */
  deliberationNeeded?: boolean;
  /** Reason explaining why deliberation is needed or skipped. */
  deliberationReason?: string;
}

/** Structured probe payload formatted for auditing. */
export interface ProbeInputPayload {
  metaDirective: string;
  historicalObservedPast: string;
  extractedContextAnchor: ExtractedContext;
}

/** Progress callback invoked during deliberation phases. */
export type ProgressCallback = (phase: string, current: number, total: number, role?: string) => void;

/** Configuration for a single probe role. */
export interface ProbeConfig {
  /** Role name (displayed in logs). */
  role: string;
  /** System prompt for this probe. Shared across all probes for KV-prefix cache reuse. */
  systemPrompt: string;
  /** Role-specific lens appended to the user message tail.
   * Contains the gate criteria and severity definitions unique to this role.
   * Placed at the tail so it does not break the shared prefix cache. */
  roleLens: string;
  /** Model provider (e.g., "openai"). */
  provider: string;
  /** Model ID (e.g., "gpt-5.4-mini"). */
  modelId: string;
}

/** Configuration for the synthesis step. */
export interface SynthesisConfig {
  /** System prompt for synthesis. */
  systemPrompt: string;
  /** Model provider (e.g., "openai"). */
  provider: string;
  /** Model ID (e.g., "gpt-5.4-mini"). */
  modelId: string;
}

/** Configuration for the context vector extraction step. */
export interface ExtractionConfig {
  /** System prompt for extraction pass. */
  systemPrompt: string;
  /** Model provider (e.g., "openai"). */
  provider: string;
  /** Model ID (e.g., "gpt-5.4-mini"). */
  modelId: string;
}

export type GovernorMode = "smart_extractor" | "always" | "periodic" | "manual";

/** Full consortium configuration. */
export interface ConsortiumConfig {
  /** Probe configurations. */
  probes: ProbeConfig[];
  /** Synthesis configuration. */
  synthesis: SynthesisConfig;
  /** Optional extraction pass configuration (defaults to synthesis model if unconfigured). */
  extraction?: ExtractionConfig;
  /** Max tokens per probe response. */
  maxProbeTokens: number;
  /** Max tokens for synthesis response. */
  maxSynthesisTokens: number;
  /** Temperature for probe responses. */
  probeTemperature: number;
  /** Temperature for synthesis response. */
  synthesisTemperature: number;
  /** Timeout per individual probe (ms). */
  probeTimeoutMs: number;
  /** Total timeout for entire deliberation (ms). */
  totalTimeoutMs: number;
  /** How probes are executed: "parallel" (all at once) or "serial" (one after another).
   * Serial benefits from KV-cache prefix reuse on local GPU servers.
   * @default "serial" */
  executionMode: "parallel" | "serial";
  /** Governor operating mode.
   * @default "smart_extractor" */
  governorMode?: GovernorMode;
  /** Maximum turns allowed between full probe audits before an audit is forced.
   * @default 20 */
  maxTurnGap?: number;
  /** Periodic turn interval when governorMode === "periodic".
   * @default 3 */
  periodicInterval?: number;
}

/** State tracked per turn. */
export interface TurnState {
  /** In-flight deliberation promise (started in input, awaited in context). */
  deliberation: Promise<DeliberationResult> | null;
}

/** Result of a single probe. */
export interface ProbeResult {
  /** Role name. */
  role: string;
  /** Probe output text (or error message). */
  text: string;
}

/* ── Telemetry types ── */

import type { Usage } from "@earendil-works/pi-ai";

/**
 * Usage accumulator state for a single deliberation.
 * Tracks successful calls and collects Usage objects.
 */
export interface UsageAccumulator {
  /** Number of successful model calls (resolved without throwing). */
  successfulCalls: number;
  /** Collected Usage objects (non-null only). */
  usages: Usage[];
  /** Add a successful call that reported usage. */
  addReported(usage: Usage): void;
  /** Add a successful call that did not report usage (all-zero or absent). */
  addUnreported(): void;
  /** Compute final status and optional aggregate. */
  compute(): { status: "not_applicable" | "unreported" | "partial" | "complete"; aggregate?: Usage };
}

/** A single telemetry event emitted during deliberation. */
export type TelemetryEvent =
  | { type: "baseline_check"; baseline_available: boolean; baseline_supplied: boolean }
  | { type: "probe_complete"; modelKey: string; duration_ms: number; output_length: number; usage_reported: boolean; usage?: Usage }
  | { type: "deliberation_telemetry"; baseline_available: boolean; baseline_supplied: boolean | "not_applicable"; successful_calls: number; reported_calls: number; usage_status: "complete" | "partial" | "unreported" | "not_applicable"; aggregate_usage?: Usage };

/** Optional telemetry callback. Exceptions must never affect deliberation. */
export type TelemetryCallback = (event: TelemetryEvent) => void;

/** Full deliberation result. */
export interface DeliberationResult {
  /** Individual probe outputs. */
  probes: ProbeResult[];
  /** Synthesized instruction/questions. */
  synthesis: string;
  /** Extracted context vectors (if extraction pass was performed). */
  extractedContext?: ExtractedContext;
  /** Errors encountered during deliberation (if any). */
  errors?: string[];
  /** True if probe deliberation was skipped by the governor gate. */
  skippedByGovernor?: boolean;
  /** Explanation of why governor skipped or triggered deliberation. */
  governorReason?: string;
}