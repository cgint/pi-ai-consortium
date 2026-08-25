// Ax AxAIService adapter over Pi's ModelCallFn transport.
// Bridges Ax's forward() pipeline to Pi's model registry, preserving
// auth, retries, telemetry, and abort semantics.

import type {
  AxAIService,
  AxAIFeatures,
  AxAIServiceOptions,
  AxAIServiceMetrics,
  AxChatRequest,
  AxChatResponse,
  AxEmbedRequest,
  AxEmbedResponse,
  AxTranscriptionRequest,
  AxTranscriptionResponse,
  AxSpeechRequest,
  AxSpeechResponse,
  AxLoggerFunction,
  AxModelConfig,
} from "@ax-llm/ax";
import type { ModelCallFn } from "./core.js";

export class AxPiService implements AxAIService<string, string, string> {
  private readonly callModel: ModelCallFn;
  private readonly modelKey: string;
  private readonly maxTokens: number;
  private readonly temperature: number;
  private options: AxAIServiceOptions = {};

  constructor(callModel: ModelCallFn, modelKey = "extraction", maxTokens = 1024, temperature = 0.2) {
    this.callModel = callModel;
    this.modelKey = modelKey;
    this.maxTokens = maxTokens;
    this.temperature = temperature;
  }

  async chat(req: Readonly<AxChatRequest<string>>, _opts?: Readonly<AxAIServiceOptions>): Promise<AxChatResponse> {
    const systemMsg = req.chatPrompt.find((m) => m.role === "system");
    const system =
      systemMsg && typeof systemMsg.content === "string" ? systemMsg.content : "";

    const nonSystem = req.chatPrompt.filter((m) => m.role !== "system");
    const user =
      nonSystem.length === 1
        ? this.contentToString(nonSystem[0].content)
        : nonSystem.map((m) => `[${m.role}]\n${this.contentToString(m.content)}`).join("\n\n---\n\n");

    const text = await this.callModel(
      this.modelKey,
      system,
      user,
      this.maxTokens,
      this.temperature,
      _opts?.abortSignal,
    );

    return { results: [{ index: 0, content: text, finishReason: "stop" }] };
  }

  getFeatures(_model?: string): AxAIFeatures {
    return {
      functions: false,
      streaming: false,
      structuredOutputs: false,
      media: {
        images: { supported: false, formats: [] },
        audio: { supported: false, formats: [] },
        files: { supported: false, formats: [], uploadMethod: "none" },
        urls: { supported: false, webSearch: false, contextFetching: false },
      },
      caching: { supported: false, types: [] },
      thinking: false,
      multiTurn: false,
    };
  }

  getName(): string {
    return "pi-consortium";
  }

  getId(): string {
    return "pi-consortium";
  }

  getModelList() {
    return undefined;
  }

  getMetrics(): AxAIServiceMetrics {
    return {
      latency: {
        chat: { mean: 0, p95: 0, p99: 0, samples: [] },
        embed: { mean: 0, p95: 0, p99: 0, samples: [] },
      },
      errors: {
        chat: { count: 0, rate: 0, total: 0 },
        embed: { count: 0, rate: 0, total: 0 },
      },
    };
  }

  getLogger(): AxLoggerFunction {
    return () => {};
  }

  getLastUsedChatModel() {
    return undefined;
  }

  getLastUsedEmbedModel() {
    return undefined;
  }

  getLastUsedModelConfig(): AxModelConfig | undefined {
    return undefined;
  }

  getEstimatedCost(): number {
    return 0;
  }

  async embed(_req: Readonly<AxEmbedRequest<string>>): Promise<AxEmbedResponse> {
    throw new Error("embed not supported by Pi transport adapter");
  }

  async transcribe(_req: Readonly<AxTranscriptionRequest<string>>): Promise<AxTranscriptionResponse> {
    throw new Error("transcribe not supported by Pi transport adapter");
  }

  async speak(_req: Readonly<AxSpeechRequest<string>>): Promise<AxSpeechResponse> {
    throw new Error("speak not supported by Pi transport adapter");
  }

  setOptions(options: Readonly<AxAIServiceOptions>): void {
    this.options = { ...this.options, ...options };
  }

  getOptions(): Readonly<AxAIServiceOptions> {
    return this.options;
  }

  private contentToString(content: unknown): string {
    if (typeof content === "string") return content;
    if (Array.isArray(content)) {
      return content
        .filter((p): p is { type: string; text?: string } => p != null && typeof p === "object" && (p as Record<string, unknown>).type === "text")
        .map((p) => p.text ?? "")
        .join("\n");
    }
    return "";
  }
}
