import { describe, expect, it } from "vitest";
import type { ModelCallFn } from "../src/core.js";
import { AxPiService } from "../src/ax-pi-service.js";

describe("AxPiService structured-output bridge", () => {
  it("maps AX's required output function to a strict Pi tool and returns its arguments as an AX function call", async () => {
    let receivedOptions: unknown;
    const callModel = (async (...args: unknown[]) => {
      receivedOptions = args[6];
      return {
        text: "",
        functionCalls: [{ id: "pi-call-1", name: "__axOutput", arguments: { answer: "structured" } }],
      };
    }) as ModelCallFn;
    const service = new AxPiService(callModel);

    const response = await service.chat({
      chatPrompt: [{ role: "user", content: "Extract context" }],
      functions: [{
        name: "__axOutput",
        description: "Emit the complete output.",
        parameters: {
          type: "object",
          properties: { answer: { type: "string", description: "The answer" } },
          required: ["answer"],
          additionalProperties: false,
        },
      }],
      functionCall: { type: "function", function: { name: "__axOutput" } },
    });

    expect(receivedOptions).toEqual({
      tools: [{
        name: "__axOutput",
        description: "Emit the complete output.",
        parameters: {
          type: "object",
          properties: { answer: { type: "string", description: "The answer" } },
          required: ["answer"],
          additionalProperties: false,
        },
        constrainedSampling: { type: "json_schema", strict: "require" },
      }],
    });
    expect(response.results[0].functionCalls).toEqual([
      {
        id: "pi-call-1",
        type: "function",
        function: { name: "__axOutput", params: '{"answer":"structured"}' },
      },
    ]);
  });

  it.each([
    ["calls a different function", [{ id: "pi-call-1", name: "unexpected", arguments: { answer: "structured" } }]],
    ["returns multiple output calls", [
      { id: "pi-call-1", name: "__axOutput", arguments: { answer: "first" } },
      { id: "pi-call-2", name: "__axOutput", arguments: { answer: "second" } },
    ]],
  ])("rejects a structured response that %s", async (_scenario, functionCalls) => {
    const callModel = (async () => ({ text: "", functionCalls })) as ModelCallFn;
    const service = new AxPiService(callModel);

    await expect(service.chat({
      chatPrompt: [{ role: "user", content: "Extract context" }],
      functions: [{
        name: "__axOutput",
        description: "Emit the complete output.",
        parameters: { type: "object", properties: {} },
      }],
      functionCall: { type: "function", function: { name: "__axOutput" } },
    })).rejects.toThrow('exactly one "__axOutput" output function call');
  });
});
