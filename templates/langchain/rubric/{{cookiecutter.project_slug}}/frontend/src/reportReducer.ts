import {
  type CandidateEvent,
  type CandidateRecord,
  type GraderFeedbackEvent,
  type ReportsByMode,
  type RubricEvaluationEndEvent,
  type RubricEvaluationStartEvent,
  type RubricEvidenceEvent,
  type RunReport,
  type UIEvent,
  decodeRunReport,
  decodeUIEvent,
} from "./contracts";

export type CandidateTimeline = {
  candidate: CandidateRecord;
  evidence: RubricEvidenceEvent[];
  evaluationStarts: RubricEvaluationStartEvent[];
  evaluations: RubricEvaluationEndEvent[];
  feedback: GraderFeedbackEvent[];
};

export type RunTimeline = {
  gradingRunId: string;
  candidatesByVersion: Record<string, CandidateTimeline>;
  pendingEventsByVersion: Record<string, UIEvent[]>;
  unboundEvents: UIEvent[];
  report: RunReport | null;
};

export type ReportState = {
  seenEventIds: Set<string>;
  runsById: Record<string, RunTimeline>;
  reportsByMode: ReportsByMode;
  diagnostic: string | null;
};

export type ReportAction =
  | { type: "event_received"; value: unknown }
  | { type: "report_received"; value: unknown }
  | { type: "clear_diagnostic" };

function emptyRunDictionary(): Record<string, RunTimeline> {
  return Object.create(null) as Record<string, RunTimeline>;
}

function hasOwnRun(
  runs: Record<string, RunTimeline>,
  gradingRunId: string,
): boolean {
  return Object.prototype.hasOwnProperty.call(runs, gradingRunId);
}

function setRun(
  runs: Record<string, RunTimeline>,
  gradingRunId: string,
  run: RunTimeline,
): Record<string, RunTimeline> {
  const next = Object.assign(emptyRunDictionary(), runs);
  next[gradingRunId] = run;
  return next;
}

export function createReportState(): ReportState {
  return {
    seenEventIds: new Set(),
    runsById: emptyRunDictionary(),
    reportsByMode: { demo: null, live: null },
    diagnostic: null,
  };
}

function emptyRun(gradingRunId: string): RunTimeline {
  return {
    gradingRunId,
    candidatesByVersion: {},
    pendingEventsByVersion: {},
    unboundEvents: [],
    report: null,
  };
}

function cloneRun(run: RunTimeline): RunTimeline {
  return {
    ...run,
    candidatesByVersion: { ...run.candidatesByVersion },
    pendingEventsByVersion: { ...run.pendingEventsByVersion },
    unboundEvents: [...run.unboundEvents],
  };
}

function emptyCandidate(candidate: CandidateRecord): CandidateTimeline {
  return {
    candidate,
    evidence: [],
    evaluationStarts: [],
    evaluations: [],
    feedback: [],
  };
}

function eventOrder(left: UIEvent, right: UIEvent): number {
  return left.iteration - right.iteration || left.eventId.localeCompare(right.eventId);
}

function attachEvent(
  timeline: CandidateTimeline,
  event: Exclude<UIEvent, CandidateEvent>,
): CandidateTimeline {
  switch (event.type) {
    case "rubric_evidence":
      return {
        ...timeline,
        evidence: [...timeline.evidence, event].sort(eventOrder),
      };
    case "rubric_evaluation_start":
      return {
        ...timeline,
        evaluationStarts: [...timeline.evaluationStarts, event].sort(eventOrder),
      };
    case "rubric_evaluation_end":
      return {
        ...timeline,
        evaluations: [...timeline.evaluations, event].sort(eventOrder),
      };
    case "grader_feedback":
      return {
        ...timeline,
        feedback: [...timeline.feedback, event].sort(eventOrder),
      };
  }
}

function candidateFromEvent(event: CandidateEvent): CandidateRecord {
  return {
    gradingRunId: event.gradingRunId,
    version: event.candidateVersion,
    iteration: event.iteration,
    candidateId: event.candidateId,
    source: event.source,
    sourceOmitted: event.sourceOmitted,
  };
}

function addCandidate(
  run: RunTimeline,
  event: CandidateEvent,
): { run: RunTimeline; diagnostic: string | null } {
  const key = String(event.candidateVersion);
  const existing = run.candidatesByVersion[key];
  if (existing !== undefined) {
    const matches =
      existing.candidate.candidateId === event.candidateId &&
      existing.candidate.source === event.source &&
      existing.candidate.sourceOmitted === event.sourceOmitted;
    return {
      run,
      diagnostic: matches
        ? "Ignored duplicate candidate version."
        : "Ignored candidate integrity mismatch.",
    };
  }

  let timeline = emptyCandidate(candidateFromEvent(event));
  let mismatch = false;
  for (const pending of run.pendingEventsByVersion[key] ?? []) {
    if (pending.type === "candidate") continue;
    if (pending.candidateId !== event.candidateId) {
      mismatch = true;
      continue;
    }
    timeline = attachEvent(timeline, pending);
  }
  run.candidatesByVersion[key] = timeline;
  delete run.pendingEventsByVersion[key];
  return {
    run,
    diagnostic: mismatch ? "Ignored candidate integrity mismatch." : null,
  };
}

function addBoundEvent(
  run: RunTimeline,
  event: Exclude<UIEvent, CandidateEvent>,
): { run: RunTimeline; diagnostic: string | null } {
  if (event.candidateVersion === null) {
    run.unboundEvents = [...run.unboundEvents, event].sort(eventOrder);
    return { run, diagnostic: null };
  }
  const key = String(event.candidateVersion);
  const timeline = run.candidatesByVersion[key];
  if (timeline === undefined) {
    run.pendingEventsByVersion[key] = [
      ...(run.pendingEventsByVersion[key] ?? []),
      event,
    ].sort(eventOrder);
    return { run, diagnostic: null };
  }
  if (timeline.candidate.candidateId !== event.candidateId) {
    return { run, diagnostic: "Ignored candidate integrity mismatch." };
  }
  run.candidatesByVersion[key] = attachEvent(timeline, event);
  return { run, diagnostic: null };
}

function addDecodedEvent(
  state: ReportState,
  event: UIEvent,
): ReportState {
  if (state.seenEventIds.has(event.eventId)) {
    return { ...state, diagnostic: "Ignored replayed event." };
  }

  const seenEventIds = new Set(state.seenEventIds);
  seenEventIds.add(event.eventId);
  const existingRun = hasOwnRun(state.runsById, event.gradingRunId)
    ? state.runsById[event.gradingRunId]
    : undefined;
  const run = cloneRun(existingRun ?? emptyRun(event.gradingRunId));
  const result =
    event.type === "candidate"
      ? addCandidate(run, event)
      : addBoundEvent(run, event);
  return {
    ...state,
    seenEventIds,
    runsById: setRun(state.runsById, event.gradingRunId, result.run),
    diagnostic: result.diagnostic,
  };
}

function evidenceEvent(report: RunReport, index: number): RubricEvidenceEvent {
  const item = report.evidence[index];
  return {
    eventId: item.eventId,
    type: "rubric_evidence",
    gradingRunId: item.gradingRunId,
    iteration: item.iteration,
    candidateVersion: item.candidateVersion,
    candidateId: item.candidateId,
    evidence: {
      requestedCandidateId: item.requestedCandidateId,
      ok: item.ok,
      behaviorFailures: [...item.behaviorFailures],
      profileFailures: [...item.profileFailures],
      durationMs: item.durationMs,
      timedOut: item.timedOut,
      outputTruncated: item.outputTruncated,
    },
  };
}

function evaluationEvent(
  report: RunReport,
  index: number,
): RubricEvaluationEndEvent {
  const item = report.evaluations[index];
  return {
    eventId: item.eventId,
    type: "rubric_evaluation_end",
    gradingRunId: item.gradingRunId,
    iteration: item.iteration,
    candidateVersion: item.candidateVersion,
    candidateId: item.candidateId,
    result: item.result,
    explanation: item.explanation,
    criteria: item.criteria.map((criterion) => ({ ...criterion })),
  };
}

function feedbackEvent(report: RunReport, index: number): GraderFeedbackEvent {
  const item = report.feedback[index];
  return {
    eventId: item.eventId,
    type: "grader_feedback",
    gradingRunId: item.gradingRunId,
    iteration: item.iteration,
    candidateVersion: item.candidateVersion,
    candidateId: item.candidateId,
    message: item.message,
  };
}

function runFromReport(report: RunReport): RunTimeline {
  const run = emptyRun(report.gradingRunId);
  run.report = report;
  for (const candidate of report.candidates) {
    run.candidatesByVersion[String(candidate.version)] = emptyCandidate({
      ...candidate,
    });
  }
  const events: Exclude<UIEvent, CandidateEvent>[] = [
    ...report.evidence.map((_, index) => evidenceEvent(report, index)),
    ...report.evaluations.map((_, index) => evaluationEvent(report, index)),
    ...report.feedback.map((_, index) => feedbackEvent(report, index)),
  ].sort(eventOrder);
  for (const event of events) {
    addBoundEvent(run, event);
  }
  return run;
}

function replaceWithReport(state: ReportState, report: RunReport): ReportState {
  const run = runFromReport(report);
  const seenEventIds = new Set(state.seenEventIds);
  for (const item of [
    ...report.evidence,
    ...report.evaluations,
    ...report.feedback,
  ]) {
    seenEventIds.add(item.eventId);
  }
  return {
    ...state,
    seenEventIds,
    runsById: setRun(state.runsById, report.gradingRunId, run),
    reportsByMode: { ...state.reportsByMode, [report.mode]: report },
    diagnostic: null,
  };
}

export function reportReducer(
  state: ReportState,
  action: ReportAction,
): ReportState {
  switch (action.type) {
    case "event_received": {
      const event = decodeUIEvent(action.value);
      return event === null
        ? { ...state, diagnostic: "Ignored malformed or unrecognized event." }
        : addDecodedEvent(state, event);
    }
    case "report_received": {
      const report = decodeRunReport(action.value);
      return report === null
        ? { ...state, diagnostic: "Ignored malformed run report." }
        : replaceWithReport(state, report);
    }
    case "clear_diagnostic":
      return { ...state, diagnostic: null };
  }
}
