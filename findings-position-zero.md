# Consortium Deliberation Injection: Cache Findings

## Decision

`index.ts` now appends the synthesized deliberation with `messages.push(syntheticMessage)`.

The previous `messages.splice(0, 0, syntheticMessage)` prepended it before the existing conversation history. For the tested provider/model, that prevents reuse of the large stable history prefix when the synthesis changes.

## Verified implementation facts

- Pi passes the system prompt separately from `event.messages`.
- `AgentMessage` user messages are passed through to the provider.
- The context handler creates a copy of `event.messages`, inserts one synthetic user message, and returns the copy.
- The handler can inject again on a later context event in the same turn: it resets `turnState.deliberation` after each completed injection, so the next context event starts a new deliberation.
- Before this change, the synthetic message was prepended with `splice(0, 0, ...)`; it is now appended with `push(...)`.

## Controlled experiment

Script: `scripts/benchmark-position-zero.ts`

Method:

1. Create a new ~60k-token simulated history **once per script invocation**.
2. Keep that history unchanged for the five requests in that invocation.
3. Change the synthetic deliberation and current user turn on every request.
4. Run `splice` and `push` in separate script invocations, so no invocation reuses the prior invocation's history cache.

This tests whether a changing deliberation before versus after a stable history affects within-run prefix-cache reuse.

### Results

- Provider/model: `omlx-local/Qwen3.6-35B-A3B-MTP-mlx-6bit`
- Endpoint: `http://127.0.0.1:4321/v1`
- Prompt size: ~47,530 tokens
- Generation: 128 tokens/request

| Layout | Run 1 | Runs 2–5 |
|---|---:|---:|
| Prepend (`splice(0,0)`) | 53.4s | 71.9–120.4s |
| Append (`push()`) | 81.8s | **4.5–4.7s** |

Prompt-token counts were effectively equal: 47,531 (prepend) vs 47,530 (append).

## Conclusion and scope

For this provider/model, placing the changing synthesis before the stable history prevents effective prefix-cache reuse. Appending it preserves the stable history prefix: the first append request is cold and later requests are about 18× faster.

This is controlled evidence for the tested endpoint/model. It does not establish identical cache behavior for every provider.

## Twins replication — separate environment (2026-08-11)

A new six-process replication used `http://twins:8081/v1`, model `qwen36-27b-nvidia-nvfp4`, `CONTEXT_SIZE=60000`, and `max_tokens=128`. Its immutable raw bundle is `.parcour-runs/position-zero-twins-20260811T1135Z/`; SHA-256 of its `SHA256SUMS.txt` is `436a470f1a4a336a8213407bb8c75feb39f086b0e5d69def54f1c0a57c666357`.

The fixed order was `push, splice, splice, push, push, splice`. Each fresh process made five serial requests; each arm therefore has three independent invocations and four warm measurements per invocation.

| Invocation | Warm median (`push`) | Warm median (`splice`) |
| --- | ---: | ---: |
| 1 | 2.666s | 17.841s |
| 2 | 2.760s | 17.982s |
| 3 | 2.950s | 18.192s |

All six processes and all 30 requests completed without a logged request error. Every `splice` generation and 29/30 `push` generations produced 128 tokens; `04-push` run 3 produced 49 tokens and is retained as an integrity qualification, not retried or excluded. The warm-median conclusion is robust to that observation: each `push` median remains 6.2–6.7× lower than its paired `splice` median.

Twins did not emit `cache_read_tokens` or `cache_write_tokens`, so this is latency evidence consistent with stable-prefix reuse, **not** direct cache-accounting evidence. It is scoped only to the named Twins endpoint/model and must not be pooled with the prior local `127.0.0.1:4321` experiment or its preserved invalid attempts.

## Evaluation principles for future benchmarks

Derived from [the deliberate-agent evaluation framework](file:///Users/cgint/dev/concepts/deliberate-agent/EVALUATION.md) and the SkillRise paper review:

- Evaluate context curation by outcomes on later **related** tasks or sessions, not by the agent's self-assessment.
- Compare against a cost-matched no-curation control; report behavioral outcomes separately from latency and cache metrics.
- Preserve raw runs and state the provider, model, task family, sample denominator, and prompt/context size.
- Treat a non-replication as evidence, not a tuning failure.

Do not infer autonomous skill evolution or use SkillRise's RL credit-assignment mechanism here: this project has no task-native verifier for open-ended agent work.

## Earlier session observation (not causal proof)

The July 20 session showed longer inter-call intervals after consortium activation, but it mixed changing context size, provider/model changes, and deliberation work. It cannot independently attribute that session slowdown to insertion position. The controlled experiment above does isolate insertion position for `omlx-local`.
