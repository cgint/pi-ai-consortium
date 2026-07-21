// Benchmark: cache impact of prepending vs appending consortium deliberation.
//
// Each invocation creates one unique, large history and retains it for all runs.
// The synthesis and current user turn change per request. Thus, a server can
// reuse the stable history only when it remains at the prompt prefix (push).
// Use separate splice/push invocations for an isolated comparison.
//
// Usage:
//   PHASE=splice npx tsx scripts/benchmark-position-zero.ts
//   PHASE=push npx tsx scripts/benchmark-position-zero.ts
//   OLLAMA_BASE=http://127.0.0.1:4321/v1 MODEL=Qwen3.6-35B-A3B-MTP-mlx-6bit PHASE=push npx tsx scripts/benchmark-position-zero.ts
//   CONTEXT_SIZE=60000 npx tsx scripts/benchmark-position-zero.ts  # adjust context padding

import https from "node:https";
import http from "node:http";
import { URL } from "node:url";

const BASE = process.env.OLLAMA_BASE ?? "http://pluto:40114/olla/openai/v1";
const MODEL = process.env.MODEL ?? "qwen36-27b-nvidia-nvfp4";
const RUNS_PER_PHASE = 5; // Repeat to smooth variance
const CONTEXT_SIZE = parseInt(process.env.CONTEXT_SIZE ?? "60000", 10);
const PHASE = process.env.PHASE ?? "both"; // "splice", "push", or "both"
// New history per script invocation; unchanged for every request in that invocation.
const HISTORY_SEED = `${Date.now()}-${Math.random().toString(36).slice(2)}`;

// --- Build realistic message arrays ---

// System prompt (same for both phases — mirrors Pi's system prompt)
const SYSTEM_PROMPT = `You are an expert coding assistant operating inside pi, a coding agent harness. You help users by reading files, executing commands, editing code, and writing new files.`;

// Consortium deliberation message (mirrors actual synthesis output)
const CONSORTIUM_DELIBERATION = `[CONSORTIUM DELIBERATION]

The consortium has reviewed your current situation. Here is their synthesized guidance:

**Navigator (WARN):** The agent is re-reading source files to answer a question already resolved. Focus on delivering the empirical verdict.

**Architect (INFO):** The position-0 splice places the synthesis before all user messages. This is semantically defensible but may affect attention distribution.

**Contrarian (NO_CONTRIBUTION)**

**Clarifier (NO_CONTRIBUTION)**

**Responder (BLOCK):** The original question about position-0 rewriting busting the KV-cache remains unanswered. Deliver the answer now.

---

**Synthesis:** Stop analyzing and answer the user's question directly. The position-0 splice is architecturally valid — the system prompt is separate. Focus on whether it causes measurable slowdown.`;

// Original user request
const USER_REQUEST = `could it be that when there is a contribution from any probe in the consortium and the synthesis is added to the llm that we somehow bust the kv-cache again by strangely rewriting the llm prompt ?`;

// Conversation history (assistant + tool results simulating a real turn)
const CONVERSATION_HISTORY = `[ASSISTANT] Let me trace the code in \`index.ts\` to find where the syntheticMessage is created and injected.

[BASH] rg -n "splice" index.ts
86: messages.splice(0, 0, syntheticMessage);

[ASSISTANT] Found it. The consortium injects at position 0 of the message array. Let me check how Pi handles this.

[READ] node_modules/@earendil-works/pi-agent-core/dist/agent-loop.js (partial)

[ASSISTANT] The message array undergoes \`transformContext\` then \`convertToLlm\`. The system prompt is handled separately. Let me verify the final structure.

[BASH] rg -n "convertToLlm" node_modules/@earendil-works/pi-agent-core/

[ASSISTANT] Confirmed: \`role: "user"\` passes through unchanged. The system prompt is a separate field.

[TOOL_RESULT] convertToLlm output: messages with role "user" preserved as-is. System prompt passed as \`systemPrompt\` field, not in messages array.

[ASSISTANT] The LLM receives: \`{ systemPrompt: "...", messages: [{role:"user", content:"[CONSORTIUM DELIBERATION]..."}, {role:"user", content:"original user input"}, ...] }\`. The synthesis is the first user message after the system prompt.`;

// Pad to simulate realistic context size (fills with benign conversation history)
function buildStableHistory(targetTokens: number): string {
  // Rough estimate: 1 token ≈ 4 chars for English text.
  const targetChars = targetTokens * 4;
  const fillerChunk = `\n[USER] Can you explain how the authentication middleware works?\n[ASSISTANT] Let me check the auth module structure. The middleware chain consists of body parsing, CORS, rate limiting, and JWT validation. Each middleware adds context or rejects early. The order matters: rate limiting before auth prevents brute-force attempts from consuming verification resources.\n[TOOL_RESULT] File read complete. Auth middleware verified. Token validation uses HS256 algorithm with rotating keys.\n`;
  let history = `[SESSION HISTORY ${HISTORY_SEED}]\n${CONVERSATION_HISTORY}`;
  while (history.length < targetChars) history += fillerChunk;
  return history.slice(0, targetChars);
}

// Stable across every request: cache reuse is possible only while this remains
// at the prompt prefix.
const STABLE_HISTORY = buildStableHistory(CONTEXT_SIZE);

// These change on every request, as a new synthesis and new user turn do in
// the agent loop. The unique nonce prevents a whole-prompt cache hit.
function dynamicDeliberation(run: number): string {
  return `${CONSORTIUM_DELIBERATION}\n\nBenchmark synthesis nonce: ${run}-${Date.now()}.`;
}

function dynamicUserTurn(run: number): string {
  return `${USER_REQUEST}\n\nBenchmark user-turn nonce: ${run}-${Date.now()}.`;
}

// --- Phase A: changing synthesis BEFORE stable history (current splice) ---
function buildSpliceZero(run: number): { system: string; messages: Array<{ role: string; content: string }> } {
  return {
    system: SYSTEM_PROMPT,
    messages: [
      { role: "user", content: dynamicDeliberation(run) },
      { role: "assistant", content: STABLE_HISTORY },
      { role: "user", content: dynamicUserTurn(run) },
    ],
  };
}

// --- Phase B: stable history remains prefix; synthesis changes at the tail ---
function buildPushEnd(run: number): { system: string; messages: Array<{ role: string; content: string }> } {
  return {
    system: SYSTEM_PROMPT,
    messages: [
      { role: "assistant", content: STABLE_HISTORY },
      { role: "user", content: dynamicUserTurn(run) },
      { role: "user", content: dynamicDeliberation(run) },
    ],
  };
}

// --- HTTP helper ---
interface Timing {
  promptTokens: number;
  completionTokens: number;
  totalMs: number;
  promptTokPerSec: number;
  genTokPerSec: number;
  cacheRead?: number;
  cacheWrite?: number;
}

async function chatCompletion(ctx: { system: string; messages: Array<{ role: string; content: string }> }): Promise<Timing> {
  const body = JSON.stringify({
    model: MODEL,
    messages: [
      { role: "system", content: ctx.system },
      ...ctx.messages,
    ],
    max_tokens: 128,
    temperature: 0,
    stream: false,
  });

  const urlStr = `${BASE}/chat/completions`;
  const urlObj = new URL(urlStr);
  const client = urlObj.protocol === "https:" ? https : http;

  const startTime = Date.now();
  const res = await new Promise<any>((resolve, reject) => {
    const req = client.request(
      {
        hostname: urlObj.hostname,
        port: urlObj.port || undefined,
        path: urlObj.pathname,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(body),
        },
      },
      (res) => {
        let data = "";
        res.on("data", (chunk) => (data += chunk));
        res.on("end", () => {
          try {
            resolve(JSON.parse(data));
          } catch {
            reject(new Error(`Parse error: ${data.slice(0, 200)}`));
          }
        });
      },
    );
    req.on("error", reject);
    req.write(body);
    req.end();
  });
  const endTime = Date.now();

  const usage = res.usage || {};
  const promptTokens = usage.prompt_tokens ?? 0;
  const completionTokens = usage.completion_tokens ?? 0;
  const totalMs = endTime - startTime;
  const totalSec = totalMs / 1000;

  return {
    promptTokens,
    completionTokens,
    totalMs,
    promptTokPerSec: totalSec > 0 ? promptTokens / totalSec : 0,
    genTokPerSec: totalSec > 0 ? completionTokens / totalSec : 0,
    cacheRead: usage.cache_read_tokens,
    cacheWrite: usage.cache_write_tokens,
  };
}

// --- Summary ---
function summarize(label: string, timings: Timing[]) {
  const totalTime = timings.reduce((s, t) => s + t.totalMs, 0);
  const avgTime = totalTime / timings.length;
  const minTime = Math.min(...timings.map((t) => t.totalMs));
  const maxTime = Math.max(...timings.map((t) => t.totalMs));
  const avgPrompt = timings.reduce((s, t) => s + t.promptTokens, 0) / timings.length;
  const avgGen = timings.reduce((s, t) => s + t.completionTokens, 0) / timings.length;
  const avgThroughput = timings.reduce((s, t) => s + t.genTokPerSec, 0) / timings.length;

  console.log(`${label}:`);
  console.log(`  Runs:            ${timings.length}`);
  console.log(`  Avg time:        ${(avgTime / 1000).toFixed(2)}s (min=${(minTime / 1000).toFixed(2)}s, max=${(maxTime / 1000).toFixed(2)}s)`);
  console.log(`  Avg prompt tok:  ${Math.round(avgPrompt)}`);
  console.log(`  Avg gen tok:     ${Math.round(avgGen)}`);
  console.log(`  Avg throughput:  ${avgThroughput.toFixed(1)} tok/s`);
  const hasCache = timings.some(t => t.cacheRead !== undefined);
  if (hasCache) {
    const avgCR = timings.reduce((s, t) => s + (t.cacheRead || 0), 0) / timings.length;
    console.log(`  Avg cache read:  ${Math.round(avgCR)}`);
  }
  console.log();

  timings.forEach((t, i) => {
    const cacheInfo = t.cacheRead !== undefined ? ` | cr:${t.cacheRead} cw:${t.cacheWrite}` : "";
    console.log(`  Run ${i}: ${t.totalMs}ms | ${t.promptTokens} prompt | ${t.completionTokens} gen | ${t.genTokPerSec.toFixed(1)} tok/s${cacheInfo}`);
  });
  console.log();
  return avgTime;
}

// --- Phase runners ---
async function runPhaseA(): Promise<number> {
  console.log("═══ PHASE A: splice(0,0) — deliberation FIRST ═══");
  console.log("(Consortium synthesis is the first user message after system prompt)\n");
  const timings: Timing[] = [];
  for (let r = 0; r < RUNS_PER_PHASE; r++) {
    process.stdout.write(`Run ${r + 1}/${RUNS_PER_PHASE}... `);
    const t = await chatCompletion(buildSpliceZero(r));
    timings.push(t);
    console.log(`${t.totalMs}ms`);
    if (r < RUNS_PER_PHASE - 1) await new Promise((res) => setTimeout(res, 1000));
  }
  return summarize("Summary A (splice)", timings);
}

async function runPhaseB(): Promise<number> {
  console.log("═══ PHASE B: push() — deliberation LAST ═══");
  console.log("(Consortium synthesis appended after all other messages)\n");
  const timings: Timing[] = [];
  for (let r = 0; r < RUNS_PER_PHASE; r++) {
    process.stdout.write(`Run ${r + 1}/${RUNS_PER_PHASE}... `);
    const t = await chatCompletion(buildPushEnd(r));
    timings.push(t);
    console.log(`${t.totalMs}ms`);
    if (r < RUNS_PER_PHASE - 1) await new Promise((res) => setTimeout(res, 1000));
  }
  return summarize("Summary B (push)", timings);
}

// --- Main ---
async function main() {
  console.log(`Position-0 Splice Benchmark`);
  console.log(`Model:     ${MODEL}`);
  console.log(`Endpoint:  ${BASE}`);
  console.log(`Context:   ~${CONTEXT_SIZE} tokens padded`);
  console.log(`Runs:      ${RUNS_PER_PHASE} per phase`);
  console.log(`Phase:     ${PHASE}\n`);

  const avgA = PHASE === "splice" || PHASE === "both" ? await runPhaseA() : null;
  const avgB = PHASE === "push" || PHASE === "both" ? await runPhaseB() : null;

  // --- Comparison ---
  if (avgA !== null && avgB !== null) {
    console.log("═══════════════════════════════════════════════");
    console.log("COMPARISON\n");

    const diffMs = avgA - avgB;
    const diffPct = ((diffMs / avgA) * 100).toFixed(1);
    const winner = diffMs > 0 ? "push()" : "splice(0,0)";

    console.log(`splice(0,0) avg: ${(avgA / 1000).toFixed(2)}s`);
    console.log(`push() avg:      ${(avgB / 1000).toFixed(2)}s`);
    console.log(`Difference:      ${Math.abs(diffMs)}ms (${diffPct}% ${diffMs > 0 ? "slower" : "faster"})`);
    console.log(`Winner:          ${winner}`);
    console.log();
    console.log("(Run with PHASE=splice or PHASE=push to observe vLLM behavior per phase.)");
  } else {
    console.log("(Single phase run — observe vLLM inference behavior for this configuration.)");
  }
}

main().catch(console.error);