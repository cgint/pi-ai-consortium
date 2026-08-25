// ConsortiumCore — pure logic, no Pi dependency.
// Orchestrates divergence (parallel probes) and convergence (synthesis).

import type { ConsortiumConfig, DeliberationResult, ProbeResult, ProgressCallback, ExtractedContext } from "./types.js";
import type { AgentMessage } from "@earendil-works/pi-agent-core";
import { extractContextFromMessages } from "./extraction.js";
import { buildActiveUserDirectionPack, buildProbeInputXml, formatAgentMessageContent } from "./context.js";
import { shouldDeliberate } from "./governor.js";

/** Schema-constrained model tool requested by a caller such as AX. */
export interface ModelCallTool {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  constrainedSampling?: false | {
    type: "json_schema";
    strict: "prefer" | "require";
  };
}

/** Optional structured-output request carried to the model transport. */
export interface ModelCallOptions {
  tools?: readonly ModelCallTool[];
}

/** Typed model output returned when a caller requested structured tool output. */
export interface ModelCallResponse {
  text: string;
  functionCalls?: readonly {
    id: string;
    name: string;
    arguments: Record<string, unknown>;
  }[];
}

/** Injectable model call function (mockable for tests). */
export type ModelCallFn = (
  modelKey: string,
  system: string,
  user: string,
  maxTokens: number,
  temperature: number,
  signal: AbortSignal | undefined,
  options?: ModelCallOptions,
) => Promise<string | ModelCallResponse>;

/** Preserve the text contract for probes and synthesis. */
function modelText(response: string | ModelCallResponse): string {
  return typeof response === "string" ? response : response.text;
}

/** Validate probe output — must start with NO_CONTRIBUTION or severity tag.
 * If the model ignored instructions and answered the user's question,
 * coerce to NO_CONTRIBUTION so it never reaches synthesis.
 *
 * Normalizes a leading "TAG " prefix (e.g. "TAG INFO x" → "INFO x")
 * before validation, recovering outputs where the model wrote the
 * placeholder literally. */
function validateProbeOutput(text: string): string {
  let trimmed = text.trim();
  // Strip leading "TAG " if followed by a recognized severity tag.
  if (trimmed.startsWith("TAG ") && /^(INFO|WARN|BLOCK)\s+\S/.test(trimmed.slice(4))) {
    trimmed = trimmed.slice(4);
  }
  // Also handle "TAG NO_CONTRIBUTION".
  if (trimmed === "TAG NO_CONTRIBUTION") {
    trimmed = "NO_CONTRIBUTION";
  }
  if (trimmed.startsWith("NO_CONTRIBUTION")) return trimmed;
  // Match severity tag followed by any non-whitespace (not just space).
  // Bare tags like "WARN\n" with no content are invalid.
  if (/^(INFO|WARN|BLOCK)\s+\S/.test(trimmed)) return trimmed;
  // Model ignored instructions or emitted bare tag — discard output
  return "NO_CONTRIBUTION";
}

const CONSORTIUM_SYNTHETIC_PREFIX = "[CONSORTIUM DELIBERATION]";

/** Return the latest human-authored user turn, normalized across Pi message content shapes. */
export function getCurrentHumanUserTurn(messages: AgentMessage[]): string {
  for (let index = messages.length - 1; index >= 0; index--) {
    const message = messages[index];
    if (message.role !== "user") continue;
    const content = formatAgentMessageContent(message);
    if (content.startsWith(CONSORTIUM_SYNTHETIC_PREFIX)) continue;
    return content;
  }
  return "";
}

export class ConsortiumCore {
  private lastExtractedContext?: ExtractedContext;

  constructor(
    private config: ConsortiumConfig,
    private callModel: ModelCallFn,
    private onBaselineCheck?: (baselineSupplied: boolean) => void,
  ) {}

  async deliberate(
    input: string | AgentMessage[],
    externalSignal?: AbortSignal,
    onProgress?: ProgressCallback,
    turnsSinceLastAudit: number = 0,
    previousContext?: ExtractedContext,
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

    // Phase 0.5 (Pre-check): Evaluate governor gate before extraction if context is not required (e.g. periodic or manual mode)
    const preGovernorDecision = shouldDeliberate(this.config, undefined, turnsSinceLastAudit);
    if (!preGovernorDecision.shouldDeliberate) {
      onProgress?.("complete", 0, 0);
      return {
        probes: [],
        synthesis: "NO_CONTRIBUTION",
        extractedContext: undefined,
        skippedByGovernor: true,
        governorReason: preGovernorDecision.reason,
        errors: errors.length > 0 ? errors : undefined,
      };
    }

    let userContext: string;
    let directionPack = "";
    let extractedContext: ExtractedContext | undefined;
    let extractionAttempts: number | undefined;
    let extractionDurationMs: number | undefined;

    if (Array.isArray(input)) {
      // Phase 0: Extraction pass
      onProgress?.("extraction", 0, 1);
      extractionAttempts = 0;
      const extractionStartedAt = Date.now();
      const extractionCallModel: ModelCallFn = async (modelKey, system, user, maxTokens, temperature, signal, options) => {
        extractionAttempts!++;
        return this.callModel(modelKey, system, user, maxTokens, temperature, signal, options);
      };
      try {
        const priorContext = previousContext ?? this.lastExtractedContext;
        const baselineSupplied = priorContext !== undefined;
        try { this.onBaselineCheck?.(baselineSupplied); } catch { /* isolated */ }
        extractedContext = await extractContextFromMessages(input, extractionCallModel, priorContext, masterController.signal);
        extractionDurationMs = Date.now() - extractionStartedAt;
        this.lastExtractedContext = extractedContext;
      } catch (err) {
        extractionDurationMs = Date.now() - extractionStartedAt;
        const msg = err instanceof Error ? err.message : String(err);
        errors.push(`Extraction: ${msg}`);
        // Extraction failed — probes would get no meaningful input.
        // Skip them; the panel will show the extraction error.
        onProgress?.("complete", 0, 0);
        return {
          probes: [],
          synthesis: "NO_CONTRIBUTION",
          extractedContext: undefined,
          extractionAttempts,
          extractionDurationMs,
          governorReason: this.config.governorMode ?? "smart_extractor",
          errors,
        };
      }
      userContext = buildProbeInputXml(input, extractedContext, false);
      directionPack = buildActiveUserDirectionPack(input, extractedContext);
    } else {
      userContext = input;
    }

    const currentUserTurn = Array.isArray(input)
      ? getCurrentHumanUserTurn(input)
      : "";

    // Phase 0.5 (Post-extraction): Re-evaluate governor gate with extracted context (e.g. for smart_extractor mode)
    const governorDecision = shouldDeliberate(this.config, extractedContext, turnsSinceLastAudit, currentUserTurn);
    if (!governorDecision.shouldDeliberate) {
      onProgress?.("complete", 0, 0);
      return {
        probes: [],
        synthesis: "NO_CONTRIBUTION",
        extractedContext,
        extractionAttempts,
        extractionDurationMs,
        skippedByGovernor: true,
        governorReason: governorDecision.reason,
        errors: errors.length > 0 ? errors : undefined,
      };
    }

    // Phase 1: Divergence — parallel or serial probes
    const probePayloadChars = Math.max(
      0,
      ...this.config.probes.map((probe) => this.formatProbeUser(userContext, probe.roleLens, directionPack).length),
    );
    const probeResults = await this.runProbes(userContext, directionPack, masterController.signal, errors, onProgress, probeTotal);

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
        extractionAttempts,
        extractionDurationMs,
        governorReason: governorDecision.reason,
        probePayloadChars,
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
      extractionAttempts,
      extractionDurationMs,
      governorReason: governorDecision.reason,
      probePayloadChars,
      errors: errors.length > 0 ? errors : undefined,
    };
  }

  private formatProbeUser(userContext: string, roleLens: string, directionPack: string): string {
    return [userContext, roleLens, directionPack]
      .filter((part) => part.length > 0)
      .join("\n\n---\n\n");
  }

  private async runProbes(
    userContext: string,
    directionPack: string,
    signal: AbortSignal,
    errors: string[],
    onProgress?: ProgressCallback,
    probeTotal?: number,
  ): Promise<ProbeResult[]> {
    const mode = this.config.executionMode ?? "serial";

    if (mode === "serial") {
      return this.runProbesSerial(userContext, directionPack, signal, errors, onProgress, probeTotal);
    }

    return this.runProbesParallel(userContext, directionPack, signal, errors, onProgress, probeTotal);
  }

  private async runProbesParallel(
    userContext: string,
    directionPack: string,
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
        const probeUser = this.formatProbeUser(userContext, probe.roleLens, directionPack);
        const result = await this.callModel(
          `probe:${i}:${probe.role}`,
          probe.systemPrompt,
          probeUser,
          this.config.maxProbeTokens,
          this.config.probeTemperature,
          probeController.signal,
        );
        const validated = validateProbeOutput(modelText(result));
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
    directionPack: string,
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
        const probeUser = this.formatProbeUser(userContext, probe.roleLens, directionPack);
        const result = await this.callModel(
          `probe:${i}:${probe.role}`,
          probe.systemPrompt,
          probeUser,
          this.config.maxProbeTokens,
          this.config.probeTemperature,
          probeController.signal,
        );
        const validated = validateProbeOutput(modelText(result));
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
      return modelText(await this.callModel(
        "synthesis",
        this.config.synthesis.systemPrompt,
        synthesisUser,
        this.config.maxSynthesisTokens,
        this.config.synthesisTemperature,
        signal,
      ));
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
