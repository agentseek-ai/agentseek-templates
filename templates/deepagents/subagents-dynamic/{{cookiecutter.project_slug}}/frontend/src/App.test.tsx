{% raw %}
import { readFileSync } from "node:fs";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const stylesheet = document.createElement("style");
stylesheet.textContent = readFileSync("src/styles.css", "utf8");
document.head.append(stylesheet);

const submittedThreadIds: Array<string | null> = [];
const submit = vi.fn();
const switchThread = vi.fn((threadId: string | null) => {
  if (threadId === null) streamState.messages = [];
  const onThreadId = capturedOptions?.onThreadId as ((value: string | null) => void) | undefined;
  onThreadId?.(threadId);
});
const streamState = {
  messages: [] as Array<Record<string, unknown>>,
  values: {},
  subagents: new Map<string, Record<string, unknown>>(),
  isLoading: false,
  error: null as Error | null,
  submit,
  switchThread,
};
let capturedOptions: Record<string, unknown> | null = null;

vi.mock("@langchain/react", () => ({
  useStream: (options: Record<string, unknown>) => {
    capturedOptions = options;
    const threadIdAtRender = (options.threadId as string | null | undefined) ?? null;
    return {
      ...streamState,
      submit: (...args: unknown[]) => {
        submittedThreadIds.push(threadIdAtRender);
        return submit(...args);
      },
    };
  },
}));

afterEach(() => {
  cleanup();
  submit.mockClear();
  submittedThreadIds.length = 0;
  switchThread.mockClear();
  capturedOptions = null;
  streamState.messages = [];
  streamState.subagents = new Map();
  streamState.isLoading = false;
  streamState.error = null;
});

describe("App", () => {
  it("offers six pattern cards without a global workflow bus", () => {
    render(<App />);

    expect(screen.getAllByRole("button", { name: /选择 .* Pattern/ })).toHaveLength(6);
    expect(screen.queryByText(/Workflow Bus/i)).toBeNull();
    expect(capturedOptions?.assistantId).toBe("classify_and_act");
  });

  it("switches to an independent assistant and submits its natural prompt", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "选择 Fan-out and synthesize Pattern" }));
    expect(capturedOptions?.assistantId).toBe("fan_out_and_synthesize");

    fireEvent.click(screen.getByRole("button", { name: "Run Fan-out and synthesize workflow" }));

    expect(submit).toHaveBeenCalledTimes(1);
    const [payload, options] = submit.mock.calls[0] as [
      { messages: Array<{ content: string }> },
      { streamSubgraphs: boolean },
    ];
    expect(payload.messages[0].content).toContain("workflow");
    expect(payload.messages[0].content).not.toContain("eval");
    expect(payload.messages[0].content).not.toContain("reviewer");
    expect(options).toEqual({ streamSubgraphs: true });
  });

  it("renders real interpreter evidence, subagent activity, and the final result", () => {
    streamState.messages = [
      { id: "human", type: "human", content: "Run a workflow" },
      {
        id: "ai-eval",
        type: "ai",
        content: "",
        tool_calls: [{ id: "eval-1", name: "eval", args: { code: "await task(...)" } }],
      },
      {
        id: "tool-eval",
        type: "tool",
        tool_call_id: "eval-1",
        content: "<result>{\"handled\":3}</result>",
      },
      { id: "final", type: "ai", content: "## Triage result\nAll three requests were handled." },
    ];
    render(<App />);

    act(() => {
      const onCustomEvent = capturedOptions?.onCustomEvent as ((event: unknown) => void) | undefined;
      onCustomEvent?.({
        id: "call-1",
        type: "subagent",
        phase: "start",
        subagent_type: "bug-fixer",
        label: "C-101",
        description: "Investigate C-101",
      });
      onCustomEvent?.({
        id: "call-1",
        type: "subagent",
        phase: "complete",
        duration_ms: 120,
      });
    });

    expect(screen.getByText("bug-fixer · C-101")).toBeTruthy();
    expect(screen.getByText("complete")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Triage result" })).toBeTruthy();
    expect(screen.getByText("运行证据 · QuickJS 与 interpreter result")).toBeTruthy();
    expect(screen.getByText("运行证据 · QuickJS 与 interpreter result").closest("details")?.open).toBe(false);
  });

  it("shows provider failures without claiming completion", () => {
    streamState.error = new Error("provider unavailable");

    render(<App />);

    expect(screen.getByRole("alert").textContent).toContain("provider unavailable");
    expect(screen.getByTestId("complete-stage").getAttribute("data-state")).toBe("waiting");
  });

  it("uses only the latest eval batch after an interpreter retry", () => {
    streamState.messages = [
      { id: "human", type: "human", content: "Run a workflow" },
      {
        id: "ai-eval-1",
        type: "ai",
        content: "",
        tool_calls: [{ id: "eval-1", name: "eval", args: { code: "await firstAttempt()" } }],
      },
      {
        id: "tool-eval-1",
        type: "tool",
        tool_call_id: "eval-1",
        content: '<error type="Error">first attempt failed</error>',
      },
      {
        id: "ai-eval-2",
        type: "ai",
        content: "Retrying",
        tool_calls: [{ id: "eval-2", name: "eval", args: { code: "await secondAttempt()" } }],
      },
      {
        id: "tool-eval-2",
        type: "tool",
        tool_call_id: "eval-2",
        content: "<result>{}</result>",
      },
      { id: "final", type: "ai", content: "Recovered and finished" },
    ];
    render(<App />);

    act(() => {
      const onCustomEvent = capturedOptions?.onCustomEvent as ((event: unknown) => void) | undefined;
      onCustomEvent?.({
        id: "failed-call",
        eval_id: "eval-1",
        type: "subagent",
        phase: "start",
        subagent_type: "reviewer",
        label: "old failed batch",
      });
      onCustomEvent?.({
        id: "failed-call",
        eval_id: "eval-1",
        type: "subagent",
        phase: "error",
      });
      onCustomEvent?.({
        id: "recovered-call",
        eval_id: "eval-2",
        type: "subagent",
        phase: "start",
        subagent_type: "reviewer",
        label: "latest successful batch",
      });
      onCustomEvent?.({
        id: "recovered-call",
        eval_id: "eval-2",
        type: "subagent",
        phase: "complete",
      });
    });

    expect(screen.queryByText("reviewer · old failed batch")).toBeNull();
    expect(screen.getByText("reviewer · latest successful batch")).toBeTruthy();
    expect(screen.getByText("1 / 1 completed")).toBeTruthy();
    expect(screen.getByTestId("complete-stage").getAttribute("data-state")).toBe("complete");
  });

  it("clears prior evidence and activities before rerunning a pattern", () => {
    streamState.messages = [
      { id: "human", type: "human", content: "Run a workflow" },
      {
        id: "ai-eval",
        type: "ai",
        content: "",
        tool_calls: [{ id: "eval-1", name: "eval", args: { code: "await task(...)" } }],
      },
      {
        id: "tool-eval",
        type: "tool",
        tool_call_id: "eval-1",
        content: "<result>{}</result>",
      },
      { id: "final", type: "ai", content: "Finished" },
    ];
    render(<App />);

    act(() => {
      const onThreadId = capturedOptions?.onThreadId as ((value: string) => void) | undefined;
      onThreadId?.("old-thread");
      const onCustomEvent = capturedOptions?.onCustomEvent as ((event: unknown) => void) | undefined;
      onCustomEvent?.({
        id: "old-call",
        type: "subagent",
        phase: "start",
        subagent_type: "bug-fixer",
        label: "old activity",
      });
      onCustomEvent?.({ id: "old-call", type: "subagent", phase: "complete" });
    });
    expect(capturedOptions?.threadId).toBe("old-thread");
    expect(screen.getByTestId("complete-stage").getAttribute("data-state")).toBe("complete");

    fireEvent.click(screen.getByRole("button", { name: "Run Classify and act workflow" }));

    expect(switchThread).toHaveBeenCalledWith(null);
    expect(submittedThreadIds).toEqual([null]);
    expect(screen.queryByText("bug-fixer · old activity")).toBeNull();
    expect(screen.getByTestId("complete-stage").getAttribute("data-state")).toBe("waiting");
  });
});
{% endraw %}
