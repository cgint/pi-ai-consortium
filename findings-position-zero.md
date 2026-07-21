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

## Earlier session observation (not causal proof)

The July 20 session showed longer inter-call intervals after consortium activation, but it mixed changing context size, provider/model changes, and deliberation work. It cannot independently attribute that session slowdown to insertion position. The controlled experiment above does isolate insertion position for `omlx-local`.
