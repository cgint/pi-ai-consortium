// ConsortiumCore — pure logic, no Pi dependency.
// Orchestrates divergence (parallel probes) and convergence (synthesis).

import type { ConsortiumConfig, DeliberationResult, ProbeResult, ProgressCallback, ExtractedContext } from "./types.js";
import type { AgentMessage } from "@earendil-works/pi-agent-core";
import { extractContextFromMessages, getDefaultExtractedContext } from "./extraction.js";
import { buildProbeInputXml } from "./context.js";

/** Injectable model call function (mockable for tests). */
export type ModelCallFn = (
  modelKey: string,
  system: string,
  user: string,
  maxTokens: number,
  temperature: number,
  signal: AbortSignal | undefined,
) => Promise<string>;

/** Validate probe output — must start with NO_CONTRIBUTION or severity tag.
 * If the model ignored instructions and answered the user's question,
 * coerce to NO_CONTRIBUTION so it never reaches synthesis. */
function validateProbeOutput(text: string): string {
  const trimmed = text.trim();
  if (trimmed.startsWith("NO_CONTRIBUTION")) return trimmed;
  // Match severity tag followed by any non-whitespace (not just space).
  // Bare tags like "WARN\n" with no content are invalid.
  if (/^(INFO|WARN|BLOCK)\s+\S/.test(trimmed)) return trimmed;
  // Model ignored instructions or emitted bare tag — discard output
  return "NO_CONTRIBUTION";
}

export class ConsortiumCore {
  constructor(
    private config: ConsortiumConfig,
    private callModel: ModelCallFn,
  ) {}

  async deliberate(
    input: string | AgentMessage[],
    externalSignal?: AbortSignal,
    onProgress?: ProgressCallback,
  ): Promise<DeliberationResult> {
    if (externalSignal?.aborted) {
      throw new Error("Deliberation aborted");
    }

    const masterController = new AbortController();
    if (externalSignal) {
      if (externalSignal.aborted) {
        masterController.abort();
      } else {
        externalSignal.addEventListener("abort", () => masterController.abort(), { once: true });
      }
    }

    const errors: string[] = [];
    const probeTotal = this.config.probes.length;

    let userContext: string;
    let extractedContext: ExtractedContext | undefined;

    if (Array.isArray(input)) {
      // Phase 0: Extraction pass
      onProgress?.("extraction", 0, 1);
      try {
        extractedContext = await extractContextFromMessages(input, this.callModel, masterController.signal);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        errors.push(`Extraction: ${msg}`);
        extractedContext = getDefaultExtractedContext(input);
      }
      userContext = buildProbeInputXml(input, extractedContext);
    } else {
      userContext = input;
    }

    // Phase 1: Divergence — parallel or serial probes
    const probeResults = await this.runProbes(userContext, masterController.signal, errors, onProgress, probeTotal);

    // Skip synthesis if all probes had nothing to contribute
    const allNoContribution = probeResults.every(
      (p) => p.text.trim().startsWith("NO_CONTRIBUTION"),
    );
    if (allNoContribution) {
      onProgress?.("complete", 0, 0);
      return {
        probes: probeResults,
        synthesis: "NO_CONTRIBUTION",
        extractedContext,
        errors: errors.length > 0 ? errors : undefined,
      };
    }

    // Phase 2: Convergence — synthesis
    onProgress?.("synthesis", 0, 1);
    const synthesisUser = this.formatProbeInputs(probeResults);
    const synthesis = await this.runSynthesis(synthesisUser, masterController.signal, errors);

    onProgress?.("complete", 0, 0);
    return {
      probes: probeResults,
      synthesis,
      extractedContext,
      errors: errors.length > 0 ? errors : undefined,
    };
  }

  private async runProbes(
    userContext: string,
    signal: AbortSignal,
    errors: string[],
    onProgress?: ProgressCallback,
    probeTotal?: number,
  ): Promise<ProbeResult[]> {
    const mode = this.config.executionMode ?? "serial";

    if (mode === "serial") {
      return this.runProbesSerial(userContext, signal, errors, onProgress, probeTotal);
    }

    return this.runProbesParallel(userContext, signal, errors, onProgress, probeTotal);
  }

  private async runProbesParallel(
    userContext: string,
    signal: AbortSignal,
    errors: string[],
    onProgress?: ProgressCallback,
    probeTotal?: number,
  ): Promise<ProbeResult[]> {
    let completed = 0;

    const probePromises = this.config.probes.map(async (probe, i) => {
      const probeController = new AbortController();
      const onMasterAbort = () => probeController.abort();
      signal.addEventListener("abort", onMasterAbort, { once: true });

      const timeoutId = setTimeout(() => probeController.abort(), this.config.probeTimeoutMs);

      try {
        const probeUser = probe.roleLens
          ? `${userContext}\n\n---\n\n${probe.roleLens}`
          : userContext;
        const result = await this.callModel(
          `probe:${i}`,
          probe.systemPrompt,
          probeUser,
          this.config.maxProbeTokens,
          this.config.probeTemperature,
          probeController.signal,
        );
        const validated = validateProbeOutput(result);
        return { role: probe.role, text: validated };
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        errors.push(`Probe "${probe.role}": ${msg}`);
        return { role: probe.role, text: `[error: ${msg}]` };
      } finally {
        clearTimeout(timeoutId);
        signal.removeEventListener("abort", onMasterAbort);
        completed++;
        onProgress?.("probe", completed, probeTotal ?? this.config.probes.length, probe.role);
      }
    });

    return Promise.all(probePromises);
  }

  private async runProbesSerial(
    userContext: string,
    signal: AbortSignal,
    errors: string[],
    onProgress?: ProgressCallback,
    probeTotal?: number,
  ): Promise<ProbeResult[]> {
    const results: ProbeResult[] = [];
    const total = probeTotal ?? this.config.probes.length;
    for (const [i, probe] of this.config.probes.entries()) {
      const probeController = new AbortController();
      const onMasterAbort = () => probeController.abort();
      signal.addEventListener("abort", onMasterAbort, { once: true });

      const timeoutId = setTimeout(() => probeController.abort(), this.config.probeTimeoutMs);

      try {
        const probeUser = probe.roleLens
          ? `${userContext}\n\n---\n\n${probe.roleLens}`
          : userContext;
        const result = await this.callModel(
          `probe:${i}`,
          probe.systemPrompt,
          probeUser,
          this.config.maxProbeTokens,
          this.config.probeTemperature,
          probeController.signal,
        );
        const validated = validateProbeOutput(result);
        results.push({ role: probe.role, text: validated });
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        errors.push(`Probe "${probe.role}": ${msg}`);
        results.push({ role: probe.role, text: `[error: ${msg}]` });
      } finally {
        clearTimeout(timeoutId);
        signal.removeEventListener("abort", onMasterAbort);
        onProgress?.("probe", i + 1, total, probe.role);
      }
    }
    return results;
  }

  private async runSynthesis(
    synthesisUser: string,
    signal: AbortSignal,
    errors: string[],
  ): Promise<string> {
    try {
      return await this.callModel(
        "synthesis",
        this.config.synthesis.systemPrompt,
        synthesisUser,
        this.config.maxSynthesisTokens,
        this.config.synthesisTemperature,
        signal,
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      errors.push(`Synthesis: ${msg}`);
      return `[Synthesis failed: ${msg}]. Raw probes follow.`;
    }
  }

  private formatProbeInputs(probes: ProbeResult[]): string {
    return probes
      .map((p) => `## ${p.role.toUpperCase()} PROBE\n${p.text}`)
      .join("\n\n---\n\n");
  }
}