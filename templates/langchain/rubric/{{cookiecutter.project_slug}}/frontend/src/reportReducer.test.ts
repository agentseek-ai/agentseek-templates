import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createElement, Fragment, useState } from "react";

import { AcceptanceGate } from "./AcceptanceGate";
import {
  BASELINE_RUBRIC,
  DEFAULT_MAX_ITERATIONS,
  type RunReport,
  decodeRunReport,
  decodeUIEvent,
} from "./contracts";
import { EvaluationTimeline } from "./EvaluationTimeline";
import { ModeSwitch } from "./ModeSwitch";
import { RubricEditor } from "./RubricEditor";
import {
  createReportState,
  reportReducer,
  type ReportState,
} from "./reportReducer";

afterEach(cleanup);

const HASH_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const HASH_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

function receiveEvent(state: ReportState, value: unknown): ReportState {
  return reportReducer(state, { type: "event_received", value });
}

function completeReport(overrides: Partial<RunReport> = {}): RunReport {
  return {
    mode: "demo",
    threadId: "outer-thread",
    innerThreadId: "inner-thread",
    gradingRunId: "run-new",
    terminalStatus: "satisfied",
    accepted: true,
    gateReason: "satisfied_with_current_evidence",
    iterations: 2,
    candidates: [
      {
        gradingRunId: "run-new",
        version: 1,
        iteration: 0,
        candidateId: HASH_A,
        source: "def find_duplicates(values):\n    return []\n",
      },
      {
        gradingRunId: "run-new",
        version: 2,
        iteration: 1,
        candidateId: HASH_B,
        source: "def find_duplicates(values):\n    return values\n",
      },
    ],
    finalCandidate: "def find_duplicates(values):\n    return values\n",
    evidence: [
      {
        eventId: "run-new:rubric_evidence:1:2:0",
        gradingRunId: "run-new",
        iteration: 1,
        candidateVersion: 2,
        candidateId: HASH_B,
        requestedCandidateId: HASH_B,
        ok: true,
        behaviorFailures: [],
        profileFailures: [],
        durationMs: 12,
        timedOut: false,
        outputTruncated: false,
      },
    ],
    evaluations: [
      {
        eventId: "run-new:rubric_evaluation_end:1:2:0",
        gradingRunId: "run-new",
        iteration: 1,
        candidateVersion: 2,
        candidateId: HASH_B,
        result: "satisfied",
        explanation: "All criteria pass.",
        criteria: [
          { criterion: "Supports nested lists", passed: true, gap: "" },
        ],
      },
    ],
    feedback: [],
    ...overrides,
  };
}

describe("wire decoders", () => {
  it("maps the complete backend event envelope into presentation fields", () => {
    const event = decodeUIEvent({
      event_id: "run-new:rubric_evidence:1:2:0",
      type: "rubric_evidence",
      grading_run_id: "run-new",
      iteration: 1,
      candidate_version: 2,
      candidate_id: HASH_B,
      payload: {
        requested_candidate_id: HASH_B,
        ok: true,
        behavior_failures: [],
        profile_failures: [],
        duration_ms: 12,
        timed_out: false,
        output_truncated: false,
      },
    });

    expect(event).toEqual({
      eventId: "run-new:rubric_evidence:1:2:0",
      type: "rubric_evidence",
      gradingRunId: "run-new",
      iteration: 1,
      candidateVersion: 2,
      candidateId: HASH_B,
      evidence: {
        requestedCandidateId: HASH_B,
        ok: true,
        behaviorFailures: [],
        profileFailures: [],
        durationMs: 12,
        timedOut: false,
        outputTruncated: false,
      },
    });
  });

  it("maps every named report field and rejects malformed nested records", () => {
    const wire = {
      mode: "demo",
      thread_id: "outer-thread",
      inner_thread_id: "inner-thread",
      grading_run_id: "run-new",
      terminal_status: "satisfied",
      accepted: true,
      gate_reason: "satisfied_with_current_evidence",
      iterations: 1,
      candidates: [
        {
          grading_run_id: "run-new",
          version: 1,
          iteration: 0,
          candidate_id: HASH_A,
          source: "def find_duplicates(values):\n    return []\n",
        },
      ],
      final_candidate: "def find_duplicates(values):\n    return []\n",
      evidence: [],
      evaluations: [],
      feedback: [],
    };

    expect(decodeRunReport(wire)).toMatchObject({
      mode: "demo",
      threadId: "outer-thread",
      innerThreadId: "inner-thread",
      gradingRunId: "run-new",
      terminalStatus: "satisfied",
      finalCandidate: "def find_duplicates(values):\n    return []\n",
      candidates: [{ candidateId: HASH_A, version: 1 }],
    });
    expect(
      decodeRunReport({
        ...wire,
        candidates: [{ ...wire.candidates[0], version: 0 }],
      }),
    ).toBeNull();
  });

  it("decodes and renders an oversized candidate as omitted rejected source", () => {
    const wire = {
      mode: "live",
      thread_id: "outer-oversized",
      inner_thread_id: "inner-oversized",
      grading_run_id: "run-oversized",
      terminal_status: "failed",
      accepted: false,
      gate_reason: "terminal_status_not_satisfied",
      iterations: 1,
      candidates: [
        {
          grading_run_id: "run-oversized",
          version: 1,
          iteration: 0,
          candidate_id: HASH_A,
          source: null,
          source_omitted: true,
        },
      ],
      final_candidate: null,
      evidence: [
        {
          event_id: "run-oversized:rubric_evidence:0:1:0",
          grading_run_id: "run-oversized",
          iteration: 0,
          candidate_version: 1,
          candidate_id: HASH_A,
          requested_candidate_id: HASH_A,
          ok: false,
          behavior_failures: [],
          profile_failures: ["candidate_too_long"],
          duration_ms: 0,
          timed_out: false,
          output_truncated: false,
        },
      ],
      evaluations: [],
      feedback: [],
    };
    const candidateEventWire = {
      event_id: "run-oversized:candidate:0:1:0",
      type: "candidate",
      grading_run_id: "run-oversized",
      iteration: 0,
      candidate_version: 1,
      candidate_id: HASH_A,
      payload: { source: null, source_omitted: true },
    };
    expect(decodeUIEvent(candidateEventWire)).toMatchObject({
      source: null,
      sourceOmitted: true,
    });
    expect(
      decodeUIEvent({
        ...candidateEventWire,
        payload: { source: null },
      }),
    ).toBeNull();
    expect(
      decodeUIEvent({
        ...candidateEventWire,
        payload: { source: "truncated-prefix", source_omitted: true },
      }),
    ).toBeNull();
    expect(decodeRunReport(wire)).toMatchObject({
      terminalStatus: "failed",
      accepted: false,
      candidates: [{ source: null, sourceOmitted: true }],
    });
    expect(
      decodeRunReport({
        ...wire,
        candidates: [{ ...wire.candidates[0], source_omitted: false }],
      }),
    ).toBeNull();

    const state = reportReducer(createReportState(), {
      type: "report_received",
      value: wire,
    });
    render(
      createElement(EvaluationTimeline, {
        run: state.runsById["run-oversized"],
      }),
    );
    expect(
      screen.getByText(
        "Candidate source omitted because it exceeded the 3,500-character limit.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("candidate_too_long")).toBeTruthy();
  });

  it("rejects passing Evidence requested for a different candidate", () => {
    const mismatchedEvidence = {
      event_id: "run-new:rubric_evidence:0:1:0",
      type: "rubric_evidence",
      grading_run_id: "run-new",
      iteration: 0,
      candidate_version: 1,
      candidate_id: HASH_A,
      payload: {
        requested_candidate_id: HASH_B,
        ok: true,
        behavior_failures: [],
        profile_failures: [],
        duration_ms: 4,
        timed_out: false,
        output_truncated: false,
      },
    };

    expect(decodeUIEvent(mismatchedEvidence)).toBeNull();

    let state = receiveEvent(createReportState(), {
      event_id: "run-new:candidate:0:1:0",
      type: "candidate",
      grading_run_id: "run-new",
      iteration: 0,
      candidate_version: 1,
      candidate_id: HASH_A,
      payload: { source: "candidate A" },
    });
    state = receiveEvent(state, mismatchedEvidence);

    expect(state.diagnostic).toBe("Ignored malformed or unrecognized event.");
    expect(state.runsById["run-new"].candidatesByVersion["1"].evidence).toEqual(
      [],
    );
    render(
      createElement(EvaluationTimeline, { run: state.runsById["run-new"] }),
    );
    expect(screen.getByText("Evidence: pending")).toBeTruthy();
    expect(screen.queryByText("Evidence: passing")).toBeNull();
  });

  it("preserves a failed candidate-binding Evidence record", () => {
    const bindingFailure = {
      event_id: "run-new:rubric_evidence:0:1:0",
      type: "rubric_evidence",
      grading_run_id: "run-new",
      iteration: 0,
      candidate_version: 1,
      candidate_id: HASH_A,
      payload: {
        requested_candidate_id: HASH_B,
        ok: false,
        behavior_failures: [],
        profile_failures: ["candidate_binding"],
        duration_ms: 0,
        timed_out: false,
        output_truncated: false,
      },
    };

    expect(decodeUIEvent(bindingFailure)).toMatchObject({
      candidateId: HASH_A,
      evidence: {
        requestedCandidateId: HASH_B,
        ok: false,
        profileFailures: ["candidate_binding"],
      },
    });

    let state = receiveEvent(createReportState(), {
      event_id: "run-new:candidate:0:1:0",
      type: "candidate",
      grading_run_id: "run-new",
      iteration: 0,
      candidate_version: 1,
      candidate_id: HASH_A,
      payload: { source: "candidate A" },
    });
    state = receiveEvent(state, bindingFailure);

    render(
      createElement(EvaluationTimeline, { run: state.runsById["run-new"] }),
    );
    expect(screen.getByText("Evidence: failing")).toBeTruthy();
    expect(screen.getByText("candidate_binding")).toBeTruthy();
  });

  it("rejects an authoritative report whose Evidence requested another candidate", () => {
    const report = completeReport({
      evidence: [
        {
          ...completeReport().evidence[0],
          requestedCandidateId: HASH_A,
        },
      ],
    });

    expect(decodeRunReport(report)).toBeNull();
    const state = reportReducer(createReportState(), {
      type: "report_received",
      value: report,
    });
    expect(state.reportsByMode.demo).toBeNull();
    expect(state.runsById["run-new"]).toBeUndefined();
    expect(state.diagnostic).toBe("Ignored malformed run report.");

    render(createElement(AcceptanceGate, { report: decodeRunReport(report) }));
    expect(screen.queryByRole("heading", { name: "Accepted" })).toBeNull();
  });

  it("rejects duplicate candidate versions in an authoritative report", () => {
    const report = completeReport({
      candidates: [
        completeReport().candidates[0],
        { ...completeReport().candidates[0] },
      ],
      evidence: [],
      evaluations: [],
      feedback: [],
    });

    expect(decodeRunReport(report)).toBeNull();
  });

  it("rejects duplicate event IDs across authoritative report record types", () => {
    const report = completeReport({
      evaluations: [
        {
          ...completeReport().evaluations[0],
          eventId: completeReport().evidence[0].eventId,
        },
      ],
    });

    expect(decodeRunReport(report)).toBeNull();
  });
});

describe("reportReducer", () => {
  it("binds shuffled events by run, version, and candidate ID", () => {
    const shuffled = [
      {
        event_id: "run-new:rubric_evidence:1:2:0",
        type: "rubric_evidence",
        grading_run_id: "run-new",
        iteration: 1,
        candidate_version: 2,
        candidate_id: HASH_B,
        payload: {
          requested_candidate_id: HASH_B,
          ok: true,
          behavior_failures: [],
          profile_failures: [],
          duration_ms: 12,
          timed_out: false,
          output_truncated: false,
        },
      },
      {
        event_id: "run-new:candidate:0:1:0",
        type: "candidate",
        grading_run_id: "run-new",
        iteration: 0,
        candidate_version: 1,
        candidate_id: HASH_A,
        payload: { source: "candidate A" },
      },
      {
        event_id: "run-new:rubric_evaluation_end:0:1:0",
        type: "rubric_evaluation_end",
        grading_run_id: "run-new",
        iteration: 0,
        candidate_version: 1,
        candidate_id: HASH_A,
        payload: {
          result: "needs_revision",
          explanation: "Use an equality-based strategy.",
          criteria: [
            {
              criterion: "Supports nested lists",
              passed: false,
              gap: "Handle unhashable values without a set.",
            },
          ],
        },
      },
      {
        event_id: "run-new:candidate:1:2:1",
        type: "candidate",
        grading_run_id: "run-new",
        iteration: 1,
        candidate_version: 2,
        candidate_id: HASH_B,
        payload: { source: "candidate B" },
      },
      {
        event_id: "run-new:grader_feedback:0:1:0",
        type: "grader_feedback",
        grading_run_id: "run-new",
        iteration: 0,
        candidate_version: 1,
        candidate_id: HASH_A,
        payload: { message: "Revise the equality check." },
      },
      {
        event_id: "run-new:rubric_evaluation_end:1:2:1",
        type: "rubric_evaluation_end",
        grading_run_id: "run-new",
        iteration: 1,
        candidate_version: 2,
        candidate_id: HASH_B,
        payload: {
          result: "satisfied",
          explanation: "All criteria pass.",
          criteria: [
            { criterion: "Supports nested lists", passed: true, gap: "" },
          ],
        },
      },
    ];

    const state = shuffled.reduce(receiveEvent, createReportState());
    const run = state.runsById["run-new"];

    expect(run.pendingEventsByVersion).toEqual({});
    expect(run.candidatesByVersion["1"]).toMatchObject({
      candidate: { candidateId: HASH_A, version: 1 },
      evidence: [],
    });
    expect(run.candidatesByVersion["1"].feedback).toHaveLength(1);
    expect(run.candidatesByVersion["1"].evaluations[0].result).toBe(
      "needs_revision",
    );
    expect(run.candidatesByVersion["2"].candidate.candidateId).toBe(HASH_B);
    expect(run.candidatesByVersion["2"].evidence).toHaveLength(1);
    expect(run.candidatesByVersion["2"].evaluations[0].result).toBe("satisfied");
  });

  it("isolates old runs and keeps equal hashes as separate candidate versions", () => {
    const events = [
      {
        event_id: "run-old:candidate:0:1:0",
        type: "candidate",
        grading_run_id: "run-old",
        iteration: 0,
        candidate_version: 1,
        candidate_id: HASH_A,
        payload: { source: "old candidate" },
      },
      {
        event_id: "run-new:candidate:0:1:0",
        type: "candidate",
        grading_run_id: "run-new",
        iteration: 0,
        candidate_version: 1,
        candidate_id: HASH_A,
        payload: { source: "same normalized candidate" },
      },
      {
        event_id: "run-new:candidate:1:2:1",
        type: "candidate",
        grading_run_id: "run-new",
        iteration: 1,
        candidate_version: 2,
        candidate_id: HASH_A,
        payload: { source: "same normalized candidate" },
      },
    ];

    const state = events.reduce(receiveEvent, createReportState());

    expect(Object.keys(state.runsById)).toEqual(["run-old", "run-new"]);
    expect(Object.keys(state.runsById["run-old"].candidatesByVersion)).toEqual([
      "1",
    ]);
    expect(Object.keys(state.runsById["run-new"].candidatesByVersion)).toEqual([
      "1",
      "2",
    ]);
  });

  it("drops replays and hash mismatches with a concise diagnostic", () => {
    const candidate = {
      event_id: "run-new:candidate:0:1:0",
      type: "candidate",
      grading_run_id: "run-new",
      iteration: 0,
      candidate_version: 1,
      candidate_id: HASH_A,
      payload: { source: "candidate A" },
    };
    let state = receiveEvent(createReportState(), candidate);
    state = receiveEvent(state, candidate);

    expect(state.runsById["run-new"].candidatesByVersion["1"].evaluations).toEqual(
      [],
    );
    expect(state.diagnostic).toBe("Ignored replayed event.");

    state = receiveEvent(state, {
      event_id: "run-new:rubric_evaluation_end:0:1:0",
      type: "rubric_evaluation_end",
      grading_run_id: "run-new",
      iteration: 0,
      candidate_version: 1,
      candidate_id: HASH_B,
      payload: {
        result: "needs_revision",
        explanation: "Mismatch",
        criteria: [],
      },
    });

    expect(state.runsById["run-new"].candidatesByVersion["1"].evaluations).toEqual(
      [],
    );
    expect(state.diagnostic).toBe("Ignored candidate integrity mismatch.");
  });

  it("atomically replaces provisional history with the authoritative report", () => {
    let state = receiveEvent(createReportState(), {
      event_id: "run-new:candidate:0:1:0",
      type: "candidate",
      grading_run_id: "run-new",
      iteration: 0,
      candidate_version: 1,
      candidate_id: HASH_A,
      payload: { source: "provisional candidate" },
    });

    state = reportReducer(state, {
      type: "report_received",
      value: completeReport(),
    });

    const run = state.runsById["run-new"];
    expect(Object.keys(run.candidatesByVersion)).toEqual(["1", "2"]);
    expect(run.candidatesByVersion["1"].candidate.source).toContain(
      "return []",
    );
    expect(run.candidatesByVersion["2"].evidence).toHaveLength(1);
    expect(run.candidatesByVersion["2"].evaluations).toHaveLength(1);
    expect(state.reportsByMode.demo?.accepted).toBe(true);
  });

  it.each(["__proto__", "constructor", "toString"])(
    "handles the prototype-like grading run ID %s as owned data",
    (gradingRunId) => {
      const state = receiveEvent(createReportState(), {
        event_id: `${gradingRunId}:candidate:0:1:0`,
        type: "candidate",
        grading_run_id: gradingRunId,
        iteration: 0,
        candidate_version: 1,
        candidate_id: HASH_A,
        payload: { source: "candidate" },
      });

      expect(
        Object.prototype.hasOwnProperty.call(state.runsById, gradingRunId),
      ).toBe(true);
      expect(
        state.runsById[gradingRunId].candidatesByVersion["1"].candidate
          .candidateId,
      ).toBe(HASH_A);
      expect(state.diagnostic).toBeNull();
    },
  );

  it("stores a concise diagnostic for malformed input without creating a run", () => {
    const state = receiveEvent(createReportState(), {
      event_id: "bad",
      type: "candidate",
      grading_run_id: "__proto__",
      iteration: -1,
      candidate_version: 0,
      candidate_id: "not-a-hash",
      payload: { source: "candidate" },
    });

    expect(state.diagnostic).toBe("Ignored malformed or unrecognized event.");
    expect(Object.keys(state.runsById)).toEqual([]);
  });
});

describe("presentation components", () => {
  it("renders the exact mode labels and disables both choices while running", () => {
    const onChange = vi.fn();
    render(
      createElement(ModeSwitch, { mode: "demo", disabled: true, onChange }),
    );

    const demo = screen.getByLabelText("Guided Demo · no key") as HTMLInputElement;
    const live = screen.getByLabelText(
      "Live Model · uses server configuration",
    ) as HTMLInputElement;
    expect(demo.disabled).toBe(true);
    expect(live.disabled).toBe(true);
    expect(demo.checked).toBe(true);
    fireEvent.click(live);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("keeps Demo controls read-only and makes Live settings editable/resettable", () => {
    function Harness() {
      const [rubric, setRubric] = useState("Changed rubric");
      const [maxIterations, setMaxIterations] = useState(7);
      return createElement(RubricEditor, {
        mode: "live",
        rubric,
        maxIterations,
        setRubric,
        setMaxIterations,
        resetBaseline: () => {
            setRubric(BASELINE_RUBRIC);
            setMaxIterations(DEFAULT_MAX_ITERATIONS);
        },
        validationText: null,
      });
    }

    const { rerender } = render(
      createElement(RubricEditor, {
        mode: "demo",
        rubric: BASELINE_RUBRIC,
        maxIterations: DEFAULT_MAX_ITERATIONS,
        setRubric: vi.fn(),
        setMaxIterations: vi.fn(),
        resetBaseline: vi.fn(),
        validationText: null,
      }),
    );
    expect((screen.getByLabelText("Task") as HTMLTextAreaElement).readOnly).toBe(
      true,
    );
    expect((screen.getByLabelText("Rubric") as HTMLTextAreaElement).readOnly).toBe(
      true,
    );
    expect(
      (screen.getByLabelText("Maximum iterations") as HTMLInputElement).readOnly,
    ).toBe(true);

    rerender(createElement(Harness));
    const rubric = screen.getByLabelText("Rubric") as HTMLTextAreaElement;
    const cap = screen.getByLabelText("Maximum iterations") as HTMLInputElement;
    expect(rubric.readOnly).toBe(false);
    expect(cap.readOnly).toBe(false);
    expect(cap.min).toBe("1");
    fireEvent.change(rubric, { target: { value: "A live rubric" } });
    fireEvent.change(cap, { target: { value: "4" } });
    expect(rubric.value).toBe("A live rubric");
    expect(cap.value).toBe("4");
    fireEvent.click(screen.getByRole("button", { name: "Reset baseline" }));
    expect(rubric.value).toBe(BASELINE_RUBRIC);
    expect(cap.value).toBe(String(DEFAULT_MAX_ITERATIONS));
  });

  it("shows versions, hashes, evidence, criteria, Gaps, and Grader feedback", () => {
    const events = [
      {
        event_id: "run-new:candidate:0:1:0",
        type: "candidate",
        grading_run_id: "run-new",
        iteration: 0,
        candidate_version: 1,
        candidate_id: HASH_A,
        payload: { source: "candidate A" },
      },
      {
        event_id: "run-new:rubric_evidence:0:1:0",
        type: "rubric_evidence",
        grading_run_id: "run-new",
        iteration: 0,
        candidate_version: 1,
        candidate_id: HASH_A,
        payload: {
          requested_candidate_id: HASH_A,
          ok: false,
          behavior_failures: ["unhashable failed"],
          profile_failures: [],
          duration_ms: 8,
          timed_out: false,
          output_truncated: false,
        },
      },
      {
        event_id: "run-new:rubric_evaluation_end:0:1:0",
        type: "rubric_evaluation_end",
        grading_run_id: "run-new",
        iteration: 0,
        candidate_version: 1,
        candidate_id: HASH_A,
        payload: {
          result: "needs_revision",
          explanation: "One criterion failed.",
          criteria: [
            {
              criterion: "Supports nested lists",
              passed: false,
              gap: "Use equality checks for unhashable values.",
            },
          ],
        },
      },
      {
        event_id: "run-new:grader_feedback:0:1:0",
        type: "grader_feedback",
        grading_run_id: "run-new",
        iteration: 0,
        candidate_version: 1,
        candidate_id: HASH_A,
        payload: { message: "Revise the nested-list branch." },
      },
    ];
    const state = events.reduce(receiveEvent, createReportState());

    render(
      createElement(EvaluationTimeline, { run: state.runsById["run-new"] }),
    );

    expect(screen.getByText("Candidate v1")).toBeTruthy();
    expect(screen.getByText("aaaaaaaa")).toBeTruthy();
    expect(screen.getByText("Evidence: failing")).toBeTruthy();
    expect(screen.getByText("Supports nested lists")).toBeTruthy();
    expect(screen.getByText("Gap")).toBeTruthy();
    expect(
      screen.getByText("Use equality checks for unhashable values."),
    ).toBeTruthy();
    expect(screen.getByText("Grader feedback")).toBeTruthy();
    expect(screen.getByText("Revise the nested-list branch.")).toBeTruthy();
    expect(screen.queryByText("You")).toBeNull();
    expect(screen.queryByText("User")).toBeNull();
  });

  it("renders all five Rubric results distinctly", () => {
    const results = [
      "satisfied",
      "needs_revision",
      "max_iterations_reached",
      "failed",
      "grader_error",
    ] as const;
    let state = receiveEvent(createReportState(), {
      event_id: "run-results:candidate:0:1:0",
      type: "candidate",
      grading_run_id: "run-results",
      iteration: 0,
      candidate_version: 1,
      candidate_id: HASH_A,
      payload: { source: "candidate" },
    });
    for (const [index, result] of results.entries()) {
      state = receiveEvent(state, {
        event_id: `run-results:rubric_evaluation_end:0:1:${index}`,
        type: "rubric_evaluation_end",
        grading_run_id: "run-results",
        iteration: 0,
        candidate_version: 1,
        candidate_id: HASH_A,
        payload: {
          result,
          explanation: `${result} explanation`,
          criteria: [],
        },
      });
    }

    render(
      createElement(EvaluationTimeline, {
        run: state.runsById["run-results"],
      }),
    );
    for (const result of results) {
      expect(screen.getByText(`Rubric result: ${result}`)).toBeTruthy();
    }
  });

  it("accepts only the coherent satisfied gate and exposes other terminal reasons", () => {
    const { rerender } = render(
      createElement(AcceptanceGate, { report: completeReport() }),
    );
    expect(screen.getByRole("heading", { name: "Accepted" })).toBeTruthy();
    expect(screen.getByText("satisfied_with_current_evidence")).toBeTruthy();

    rerender(
      createElement(AcceptanceGate, {
        report: completeReport({
          accepted: false,
          gateReason: "current_evidence_missing",
        }),
      }),
    );
    expect(screen.getByRole("heading", { name: "Not accepted" })).toBeTruthy();
    expect(screen.getByText("current_evidence_missing")).toBeTruthy();

    rerender(
      createElement(AcceptanceGate, {
        report: completeReport({
          terminalStatus: "failed",
          accepted: true,
          gateReason: "terminal_status_not_satisfied",
        }),
      }),
    );
    expect(
      screen.getByRole("heading", { name: "Report contract error" }),
    ).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Accepted" })).toBeNull();
  });

  it("keeps the last candidate visible when the report is not accepted", () => {
    const report = completeReport({
      terminalStatus: "max_iterations_reached",
      accepted: false,
      gateReason: "terminal_status_not_satisfied",
    });
    let state = createReportState();
    state = reportReducer(state, { type: "report_received", value: report });

    render(
      createElement(
        Fragment,
        null,
        createElement(EvaluationTimeline, {
          run: state.runsById["run-new"],
        }),
        createElement(AcceptanceGate, { report }),
      ),
    );

    expect(screen.getByText("Candidate v2")).toBeTruthy();
    expect(screen.getByText("bbbbbbbb")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Not accepted" })).toBeTruthy();
    expect(screen.getByText("max_iterations_reached")).toBeTruthy();
  });
});
