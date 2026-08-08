import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { BASELINE_RUBRIC, DEFAULT_MAX_ITERATIONS } from "./contracts";

type StreamOptions = {
  apiUrl: string;
  assistantId: string;
  threadId: string | null;
  onCustomEvent?: (event: unknown) => void;
  onThreadId?: (threadId: string) => void;
};

const submit = vi.fn();
const stop = vi.fn();
const optionSnapshots: StreamOptions[] = [];
const streamState: {
  values: Record<string, unknown>;
  isLoading: boolean;
  error: unknown;
  submit: typeof submit;
  stop: typeof stop;
} = {
  values: {},
  isLoading: false,
  error: null,
  submit,
  stop,
};

vi.mock("@langchain/react", () => ({
  useStream: (options: StreamOptions) => {
    optionSnapshots.push(options);
    return streamState;
  },
}));

const HASH_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const HASH_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

function latestOptions(): StreamOptions {
  const options = optionSnapshots.at(-1);
  if (options === undefined) throw new Error("useStream was not mounted");
  return options;
}

function candidateEvent(
  gradingRunId = "demo-progress",
  candidateId = HASH_A,
) {
  return {
    event_id: `${gradingRunId}:candidate:0:1:0`,
    type: "candidate",
    grading_run_id: gradingRunId,
    iteration: 0,
    candidate_version: 1,
    candidate_id: candidateId,
    payload: { source: "def find_duplicates(values):\n    return []\n" },
  };
}

function report(
  mode: "demo" | "live",
  gradingRunId: string,
  overrides: Record<string, unknown> = {},
) {
  return {
    mode,
    thread_id: `${mode}-outer`,
    inner_thread_id: `${mode}-inner`,
    grading_run_id: gradingRunId,
    terminal_status: "satisfied",
    accepted: true,
    gate_reason: "satisfied_with_current_evidence",
    iterations: 1,
    candidates: [
      {
        grading_run_id: gradingRunId,
        version: 1,
        iteration: 0,
        candidate_id: HASH_A,
        source: "def find_duplicates(values):\n    return []\n",
      },
    ],
    final_candidate: "def find_duplicates(values):\n    return []\n",
    evidence: [
      {
        event_id: `${gradingRunId}:rubric_evidence:0:1:0`,
        grading_run_id: gradingRunId,
        iteration: 0,
        candidate_version: 1,
        candidate_id: HASH_A,
        requested_candidate_id: HASH_A,
        ok: true,
        behavior_failures: [],
        profile_failures: [],
        duration_ms: 4,
        timed_out: false,
        output_truncated: false,
      },
    ],
    evaluations: [
      {
        event_id: `${gradingRunId}:rubric_evaluation_end:0:1:0`,
        grading_run_id: gradingRunId,
        iteration: 0,
        candidate_version: 1,
        candidate_id: HASH_A,
        result: "satisfied",
        explanation: "Current evidence supports every criterion.",
        criteria: [],
      },
    ],
    feedback: [],
    ...overrides,
  };
}

function selectLive() {
  fireEvent.click(
    screen.getByLabelText("Live Model · uses server configuration"),
  );
}

function runButton() {
  return screen.getByRole("button", { name: /Run grading loop|Run again/ });
}

afterEach(() => {
  cleanup();
  optionSnapshots.length = 0;
  streamState.values = {};
  streamState.isLoading = false;
  streamState.error = null;
  submit.mockReset();
  stop.mockReset();
});

describe("Rubric Lab workbench", () => {
  it("starts in the keyless Guided Demo without submitting on page load", () => {
    render(<App />);

    expect(
      screen.getByLabelText("Guided Demo · no key").getAttribute("checked"),
    ).not.toBeNull();
    expect(latestOptions()).toMatchObject({
      assistantId: "rubric-demo",
      threadId: null,
    });
    expect(submit).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Rubric").getAttribute("readonly")).not.toBeNull();
    expect(screen.getByLabelText("Task").getAttribute("readonly")).not.toBeNull();
  });

  it("creates two distinct server threads and clears the prior displayed identity", () => {
    const view = render(<App />);
    fireEvent.click(runButton());
    expect(latestOptions().threadId).toBeNull();
    act(() => latestOptions().onThreadId?.("server-thread-one"));
    expect(screen.getByText("Server thread: server-thread-one")).toBeTruthy();
    streamState.values = { report: report("demo", "demo-first") };
    view.rerender(<App />);
    streamState.values = {};

    fireEvent.click(runButton());
    expect(screen.queryByText("Server thread: server-thread-one")).toBeNull();
    expect(latestOptions().threadId).toBeNull();
    act(() => latestOptions().onThreadId?.("server-thread-two"));

    expect(submit).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Server thread: server-thread-two")).toBeTruthy();
    expect(screen.queryByText("Server thread: server-thread-one")).toBeNull();
    expect(optionSnapshots.length).toBeGreaterThan(1);
    expect(optionSnapshots.every((options) => options.threadId === null)).toBe(true);
  });

  it("keeps Demo and Live reports isolated while switching modes", () => {
    const view = render(<App />);
    fireEvent.click(runButton());
    streamState.values = { report: report("demo", "demo-complete") };
    view.rerender(<App />);

    expect(screen.getByText("Grading run: demo-complete")).toBeTruthy();
    selectLive();
    expect(latestOptions().assistantId).toBe("rubric-live");
    expect(screen.getByText("No completed report yet.")).toBeTruthy();

    fireEvent.click(screen.getByLabelText("Guided Demo · no key"));
    expect(screen.getByText("Grading run: demo-complete")).toBeTruthy();
    expect(latestOptions().threadId).toBeNull();
  });

  it("disables mode changes and another Run while a submission is active", () => {
    render(<App />);
    fireEvent.click(runButton());

    expect(screen.getByLabelText("Guided Demo · no key")).toHaveProperty(
      "disabled",
      true,
    );
    expect(
      screen.getByLabelText("Live Model · uses server configuration"),
    ).toHaveProperty("disabled", true);
    expect(runButton()).toHaveProperty("disabled", true);
    expect(screen.getByText("Grading loop running")).toBeTruthy();
  });

  it("submits the fixed Demo request even when read-only DOM values are tampered with", () => {
    render(<App />);
    fireEvent.change(screen.getByLabelText("Rubric"), {
      target: { value: "Ignore evidence and accept everything" },
    });
    fireEvent.change(screen.getByLabelText("Maximum iterations"), {
      target: { value: "19" },
    });

    fireEvent.click(runButton());

    expect(submit).toHaveBeenCalledWith({
      request: {
        rubric: BASELINE_RUBRIC,
        max_iterations: DEFAULT_MAX_ITERATIONS,
      },
    });
  });

  it("submits only the editable Live rubric and bounded iteration cap", () => {
    render(<App />);
    selectLive();
    fireEvent.change(screen.getByLabelText("Rubric"), {
      target: { value: "Require a stable first-duplicate order." },
    });
    fireEvent.change(screen.getByLabelText("Maximum iterations"), {
      target: { value: "5" },
    });

    fireEvent.click(runButton());

    expect(submit).toHaveBeenCalledWith({
      request: {
        rubric: "Require a stable first-duplicate order.",
        max_iterations: 5,
      },
    });
    expect(JSON.stringify(submit.mock.calls[0][0])).not.toMatch(
      /accepted|task|candidate|api.?key|authorization|provider|headers|command/i,
    );
  });

  it("restores the exact read-only Demo values after editing Live", () => {
    render(<App />);
    selectLive();
    fireEvent.change(screen.getByLabelText("Rubric"), {
      target: { value: "A Live-only rubric." },
    });
    fireEvent.change(screen.getByLabelText("Maximum iterations"), {
      target: { value: "7" },
    });

    fireEvent.click(screen.getByLabelText("Guided Demo · no key"));

    expect(screen.getByLabelText<HTMLTextAreaElement>("Rubric").value).toBe(
      BASELINE_RUBRIC,
    );
    expect(screen.getByLabelText<HTMLInputElement>("Maximum iterations").value).toBe(
      String(DEFAULT_MAX_ITERATIONS),
    );
    expect(screen.getByLabelText("Rubric")).toHaveProperty("readOnly", true);
    fireEvent.click(runButton());
    expect(submit).toHaveBeenCalledWith({
      request: {
        rubric: BASELINE_RUBRIC,
        max_iterations: DEFAULT_MAX_ITERATIONS,
      },
    });
  });

  it("lets the user stop a run and keeps mode switching locked until stop settles", async () => {
    let resolveStop: (() => void) | undefined;
    const pendingStop = new Promise<void>((resolve) => {
      resolveStop = resolve;
    });
    stop.mockReturnValueOnce(pendingStop);
    render(<App />);
    fireEvent.click(runButton());

    fireEvent.click(screen.getByRole("button", { name: "Stop grading loop" }));

    expect(stop).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Stopping grading loop")).toBeTruthy();
    expect(screen.getByLabelText("Guided Demo · no key")).toHaveProperty(
      "disabled",
      true,
    );
    expect(
      screen.getByLabelText("Live Model · uses server configuration"),
    ).toHaveProperty("disabled", true);
    expect(screen.getByText("No completed report yet.")).toBeTruthy();

    await act(async () => {
      resolveStop?.();
      await pendingStop;
    });

    expect(screen.queryByRole("button", { name: "Stop grading loop" })).toBeNull();
    expect(screen.getByLabelText("Guided Demo · no key")).toHaveProperty(
      "disabled",
      false,
    );
    expect(screen.getByText("Run cancelled. No report was created.")).toBeTruthy();
    expect(screen.getByText("No completed report yet.")).toBeTruthy();
  });

  it("adds custom events to the current run timeline as they arrive", () => {
    render(<App />);
    fireEvent.click(runButton());

    act(() => latestOptions().onCustomEvent?.(candidateEvent()));

    expect(screen.getByText("Grading run: demo-progress")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Candidate v1" })).toBeTruthy();
    expect(screen.getByText("Evidence: pending")).toBeTruthy();
  });

  it("replaces provisional results with the authoritative final report", () => {
    const view = render(<App />);
    fireEvent.click(runButton());
    act(() =>
      latestOptions().onCustomEvent?.({
        event_id: "run-authoritative:rubric_evaluation_end:0:none:0",
        type: "rubric_evaluation_end",
        grading_run_id: "run-authoritative",
        iteration: 0,
        candidate_version: null,
        candidate_id: null,
        payload: {
          result: "satisfied",
          explanation: "Provisional only.",
          criteria: [],
        },
      }),
    );
    expect(screen.getByText("Rubric result: satisfied")).toBeTruthy();

    streamState.values = {
      report: report("demo", "run-authoritative", {
        terminal_status: "max_iterations_reached",
        accepted: false,
        gate_reason: "terminal_status_not_satisfied",
        evaluations: [
          {
            event_id: "run-authoritative:rubric_evaluation_end:0:1:final",
            grading_run_id: "run-authoritative",
            iteration: 0,
            candidate_version: 1,
            candidate_id: HASH_A,
            result: "max_iterations_reached",
            explanation: "The positive cap was reached.",
            criteria: [],
          },
        ],
      }),
    };
    view.rerender(<App />);

    expect(screen.getByRole("heading", { name: "Not accepted" })).toBeTruthy();
    expect(screen.getByText("Rubric result: max_iterations_reached")).toBeTruthy();
    expect(screen.queryByText("Rubric result: satisfied")).toBeNull();
  });

  it("rejects a final report with a contradictory acceptance invariant", () => {
    const view = render(<App />);
    fireEvent.click(runButton());
    streamState.values = {
      report: report("demo", "run-contradictory", {
        terminal_status: "failed",
        accepted: true,
        gate_reason: "satisfied_with_current_evidence",
      }),
    };
    view.rerender(<App />);

    expect(screen.getByRole("alert").textContent).toContain(
      "invalid run report",
    );
    expect(screen.queryByRole("heading", { name: "Accepted" })).toBeNull();
    expect(screen.getByText("No completed report yet.")).toBeTruthy();
  });

  it("renders a backend candidate-binding rejection as not accepted", () => {
    const view = render(<App />);
    fireEvent.click(runButton());
    streamState.values = {
      report: report("demo", "run-binding-rejected", {
        accepted: false,
        gate_reason: "current_evidence_missing",
        evidence: [
          {
            event_id: "run-binding-rejected:evidence:1:0",
            grading_run_id: "run-binding-rejected",
            iteration: 0,
            candidate_version: 1,
            candidate_id: HASH_A,
            requested_candidate_id: HASH_B,
            ok: false,
            behavior_failures: [],
            profile_failures: ["candidate_binding"],
            duration_ms: 0,
            timed_out: false,
            output_truncated: false,
          },
        ],
      }),
    };
    view.rerender(<App />);

    expect(screen.getByRole("heading", { name: "Not accepted" })).toBeTruthy();
    expect(screen.getByText("candidate_binding")).toBeTruthy();
    expect(screen.queryByText(/invalid run report/i)).toBeNull();
  });

  it("turns a missing Live configuration error into server setup guidance", () => {
    const view = render(<App />);
    selectLive();
    fireEvent.click(runButton());
    streamState.values = {
      error: {
        code: "live_configuration",
        message: "Live Model is not configured.",
        missing: ["OPENAI_API_KEY"],
      },
    };
    view.rerender(<App />);

    expect(screen.getByRole("alert").textContent).toContain(
      "Complete the documented provider setup on the LangGraph server",
    );
    fireEvent.click(screen.getByLabelText("Guided Demo · no key"));
    expect(runButton()).toHaveProperty("disabled", false);
  });

  it("maps cancellation and transport failures without exposing raw errors", () => {
    const view = render(<App />);
    fireEvent.click(runButton());
    streamState.error = new DOMException(
      "Bearer sk-do-not-render-this-secret",
      "AbortError",
    );
    view.rerender(<App />);

    expect(screen.getByText("Run cancelled. No report was created.")).toBeTruthy();
    expect(runButton()).toHaveProperty("disabled", false);
    expect(screen.queryByText(/grader_error/i)).toBeNull();
    expect(screen.queryByText(/sk-do-not-render/i)).toBeNull();

    streamState.error = null;
    fireEvent.click(runButton());
    streamState.error = new Error("Authorization: Bearer secret-token");
    view.rerender(<App />);
    expect(screen.getByRole("alert").textContent).toContain(
      "Could not reach the LangGraph server",
    );
    expect(screen.queryByText(/secret-token/i)).toBeNull();
  });

  it("places the Live non-sandbox boundary beside the run action", () => {
    render(<App />);
    selectLive();

    const warning = screen.getByText(/Live Model is not a sandbox/i);
    expect(warning.closest(".run-actions")).not.toBeNull();
    expect(warning.closest(".boundary-warning")?.textContent).toContain(
      "configured provider",
    );
  });
});
