// Consortium types — pure interfaces, no runtime dependencies.

/** Configuration for a single probe role. */
export interface ProbeConfig {
  /** Role name (displayed in logs). */
  role: string;
  /** System prompt for this probe. */
  systemPrompt: string;
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

/** Full consortium configuration. */
export interface ConsortiumConfig {
  /** Probe configurations. */
  probes: ProbeConfig[];
  /** Synthesis configuration. */
  synthesis: SynthesisConfig;
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

/** Full deliberation result. */
export interface DeliberationResult {
  /** Individual probe outputs. */
  probes: ProbeResult[];
  /** Synthesized instruction/questions. */
  synthesis: string;
  /** Errors encountered during deliberation (if any). */
  errors?: string[];
}