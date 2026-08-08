export const TASK_PROMPT =
  "Implement find_duplicates(values). Return valid Python source only.";

export const BASELINE_RUBRIC = `- The response is valid Python source that defines find_duplicates(values).
- Each duplicated value appears exactly once in the returned list.
- Result order follows when each value first becomes a duplicate.
- Unhashable values such as nested lists are supported.
- The input sequence is not mutated.
- Before satisfied, call run_test_suite with the exact current candidate and receive ok=true.
`;

export const DEFAULT_MAX_ITERATIONS = 3;
export const MAX_ITERATIONS = 20;

export type RunMode = "demo" | "live";
export type RubricResult =
  | "satisfied"
  | "needs_revision"
  | "max_iterations_reached"
  | "failed"
  | "grader_error";
export type TerminalStatus = Exclude<RubricResult, "needs_revision">;
export type GateReason =
  | "satisfied_with_current_evidence"
  | "terminal_status_not_satisfied"
  | "current_evidence_missing";

export type WireUIEvent = {
  event_id: string;
  type: string;
  grading_run_id: string;
  iteration: number;
  candidate_version: number | null;
  candidate_id: string | null;
  payload: unknown;
};

type EventBase = {
  eventId: string;
  gradingRunId: string;
  iteration: number;
};

export type CandidateEvent = EventBase & {
  type: "candidate";
  candidateVersion: number;
  candidateId: string;
  source: string | null;
  sourceOmitted?: boolean;
};

export type GraderFeedbackEvent = EventBase & {
  type: "grader_feedback";
  candidateVersion: number | null;
  candidateId: string | null;
  message: string;
};

export type EvidenceResult = {
  requestedCandidateId: string;
  ok: boolean;
  behaviorFailures: string[];
  profileFailures: string[];
  durationMs: number;
  timedOut: boolean;
  outputTruncated: boolean;
};

export type RubricEvidenceEvent = EventBase & {
  type: "rubric_evidence";
  candidateVersion: number;
  candidateId: string;
  evidence: EvidenceResult;
};

export type RubricEvaluationStartEvent = EventBase & {
  type: "rubric_evaluation_start";
  candidateVersion: number | null;
  candidateId: string | null;
};

export type CriterionResult = {
  criterion: string;
  passed: boolean;
  gap: string;
};

export type RubricEvaluationEndEvent = EventBase & {
  type: "rubric_evaluation_end";
  candidateVersion: number | null;
  candidateId: string | null;
  result: RubricResult;
  explanation: string;
  criteria: CriterionResult[];
};

export type UIEvent =
  | CandidateEvent
  | GraderFeedbackEvent
  | RubricEvidenceEvent
  | RubricEvaluationStartEvent
  | RubricEvaluationEndEvent;

export type CandidateRecord = {
  gradingRunId: string;
  version: number;
  iteration: number;
  candidateId: string;
  source: string | null;
  sourceOmitted?: boolean;
};

export type EvidenceRecord = EvidenceResult & {
  eventId: string;
  gradingRunId: string;
  iteration: number;
  candidateVersion: number;
  candidateId: string;
};

export type EvaluationRecord = {
  eventId: string;
  gradingRunId: string;
  iteration: number;
  candidateVersion: number | null;
  candidateId: string | null;
  result: RubricResult;
  explanation: string;
  criteria: CriterionResult[];
};

export type FeedbackRecord = {
  eventId: string;
  gradingRunId: string;
  iteration: number;
  candidateVersion: number | null;
  candidateId: string | null;
  message: string;
};

export type RunReport = {
  mode: RunMode;
  threadId: string;
  innerThreadId: string;
  gradingRunId: string;
  terminalStatus: TerminalStatus;
  accepted: boolean;
  gateReason: GateReason;
  iterations: number;
  candidates: CandidateRecord[];
  finalCandidate: string | null;
  evidence: EvidenceRecord[];
  evaluations: EvaluationRecord[];
  feedback: FeedbackRecord[];
};

export type ReportsByMode = Record<RunMode, RunReport | null>;

const RUBRIC_RESULTS = new Set<RubricResult>([
  "satisfied",
  "needs_revision",
  "max_iterations_reached",
  "failed",
  "grader_error",
]);
const TERMINAL_STATUSES = new Set<TerminalStatus>([
  "satisfied",
  "max_iterations_reached",
  "failed",
  "grader_error",
]);
const GATE_REASONS = new Set<GateReason>([
  "satisfied_with_current_evidence",
  "terminal_status_not_satisfied",
  "current_evidence_missing",
]);
const CANDIDATE_ID = /^[0-9a-f]{64}$/;

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function isCandidateId(value: unknown): value is string {
  return typeof value === "string" && CANDIDATE_ID.test(value);
}

function candidateSource(
  value: unknown,
  sourceOmitted: boolean,
): string | null | undefined {
  if (sourceOmitted) return value === null ? null : undefined;
  return typeof value === "string" ? value : undefined;
}

function isNonNegativeInteger(value: unknown): value is number {
  return Number.isInteger(value) && (value as number) >= 0;
}

function isPositiveInteger(value: unknown): value is number {
  return Number.isInteger(value) && (value as number) >= 1;
}

function stringArray(value: unknown): string[] | null {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
    return null;
  }
  return [...value];
}

function candidateBinding(
  version: unknown,
  candidateId: unknown,
): { candidateVersion: number | null; candidateId: string | null } | null {
  if (version === null && candidateId === null) {
    return { candidateVersion: null, candidateId: null };
  }
  if (!isPositiveInteger(version) || !isCandidateId(candidateId)) {
    return null;
  }
  return { candidateVersion: version, candidateId };
}

function criterion(value: unknown): CriterionResult | null {
  if (
    !isObject(value) ||
    typeof value.criterion !== "string" ||
    typeof value.passed !== "boolean" ||
    typeof value.gap !== "string"
  ) {
    return null;
  }
  return {
    criterion: value.criterion,
    passed: value.passed,
    gap: value.gap,
  };
}

function criteria(value: unknown): CriterionResult[] | null {
  if (!Array.isArray(value)) return null;
  const decoded = value.map(criterion);
  return decoded.every((item): item is CriterionResult => item !== null)
    ? decoded
    : null;
}

function evidenceResult(value: unknown): EvidenceResult | null {
  if (!isObject(value)) return null;
  const behaviorFailures = stringArray(value.behavior_failures);
  const profileFailures = stringArray(value.profile_failures);
  if (
    !isCandidateId(value.requested_candidate_id) ||
    typeof value.ok !== "boolean" ||
    behaviorFailures === null ||
    profileFailures === null ||
    !isNonNegativeInteger(value.duration_ms) ||
    typeof value.timed_out !== "boolean" ||
    typeof value.output_truncated !== "boolean"
  ) {
    return null;
  }
  return {
    requestedCandidateId: value.requested_candidate_id,
    ok: value.ok,
    behaviorFailures,
    profileFailures,
    durationMs: value.duration_ms,
    timedOut: value.timed_out,
    outputTruncated: value.output_truncated,
  };
}

function evidenceMatchesCandidate(
  evidence: EvidenceResult,
  candidateId: string,
): boolean {
  return (
    evidence.requestedCandidateId === candidateId ||
    (!evidence.ok && evidence.profileFailures.includes("candidate_binding"))
  );
}

function eventEnvelope(value: unknown): {
  wire: WireUIEvent;
  binding: { candidateVersion: number | null; candidateId: string | null };
} | null {
  if (
    !isObject(value) ||
    !isNonEmptyString(value.event_id) ||
    typeof value.type !== "string" ||
    !isNonEmptyString(value.grading_run_id) ||
    !isNonNegativeInteger(value.iteration)
  ) {
    return null;
  }
  const binding = candidateBinding(value.candidate_version, value.candidate_id);
  if (binding === null) return null;
  return {
    wire: {
      event_id: value.event_id,
      type: value.type,
      grading_run_id: value.grading_run_id,
      iteration: value.iteration,
      candidate_version: binding.candidateVersion,
      candidate_id: binding.candidateId,
      payload: value.payload,
    },
    binding,
  };
}

export function decodeUIEvent(value: unknown): UIEvent | null {
  const envelope = eventEnvelope(value);
  if (envelope === null) return null;
  const { wire, binding } = envelope;
  const payload = wire.payload;
  if (!isObject(payload)) return null;
  const base = {
    eventId: wire.event_id,
    gradingRunId: wire.grading_run_id,
    iteration: wire.iteration,
  };

  switch (wire.type) {
    case "candidate":
      if (
        payload.source_omitted !== undefined &&
        typeof payload.source_omitted !== "boolean"
      ) {
        return null;
      }
      const sourceOmitted = payload.source_omitted === true;
      const source = candidateSource(payload.source, sourceOmitted);
      if (
        binding.candidateVersion === null ||
        binding.candidateId === null ||
        source === undefined
      ) {
        return null;
      }
      return {
        ...base,
        type: "candidate",
        candidateVersion: binding.candidateVersion,
        candidateId: binding.candidateId,
        source,
        sourceOmitted,
      };
    case "grader_feedback":
      if (typeof payload.message !== "string") return null;
      return {
        ...base,
        type: "grader_feedback",
        ...binding,
        message: payload.message,
      };
    case "rubric_evidence": {
      const evidence = evidenceResult(payload);
      if (
        evidence === null ||
        binding.candidateVersion === null ||
        binding.candidateId === null ||
        !evidenceMatchesCandidate(evidence, binding.candidateId)
      ) {
        return null;
      }
      return {
        ...base,
        type: "rubric_evidence",
        candidateVersion: binding.candidateVersion,
        candidateId: binding.candidateId,
        evidence,
      };
    }
    case "rubric_evaluation_start":
      return {
        ...base,
        type: "rubric_evaluation_start",
        ...binding,
      };
    case "rubric_evaluation_end": {
      const decodedCriteria = criteria(payload.criteria);
      if (
        !RUBRIC_RESULTS.has(payload.result as RubricResult) ||
        typeof payload.explanation !== "string" ||
        decodedCriteria === null
      ) {
        return null;
      }
      return {
        ...base,
        type: "rubric_evaluation_end",
        ...binding,
        result: payload.result as RubricResult,
        explanation: payload.explanation,
        criteria: decodedCriteria,
      };
    }
    default:
      return null;
  }
}

function candidateRecord(value: unknown): CandidateRecord | null {
  if (
    !isObject(value) ||
    (value.source_omitted !== undefined &&
      typeof value.source_omitted !== "boolean")
  ) {
    return null;
  }
  const sourceOmitted = value.source_omitted === true;
  const source = candidateSource(value.source, sourceOmitted);
  if (
    !isNonEmptyString(value.grading_run_id) ||
    !isPositiveInteger(value.version) ||
    !isNonNegativeInteger(value.iteration) ||
    !isCandidateId(value.candidate_id) ||
    source === undefined
  ) {
    return null;
  }
  return {
    gradingRunId: value.grading_run_id,
    version: value.version,
    iteration: value.iteration,
    candidateId: value.candidate_id,
    source,
    sourceOmitted,
  };
}

function evidenceRecord(value: unknown): EvidenceRecord | null {
  if (
    !isObject(value) ||
    !isNonEmptyString(value.event_id) ||
    !isNonEmptyString(value.grading_run_id) ||
    !isNonNegativeInteger(value.iteration) ||
    !isPositiveInteger(value.candidate_version) ||
    !isCandidateId(value.candidate_id)
  ) {
    return null;
  }
  const decodedEvidence = evidenceResult(value);
  if (decodedEvidence === null) return null;
  return {
    eventId: value.event_id,
    gradingRunId: value.grading_run_id,
    iteration: value.iteration,
    candidateVersion: value.candidate_version,
    candidateId: value.candidate_id,
    ...decodedEvidence,
  };
}

function evaluationRecord(value: unknown): EvaluationRecord | null {
  if (
    !isObject(value) ||
    !isNonEmptyString(value.event_id) ||
    !isNonEmptyString(value.grading_run_id) ||
    !isNonNegativeInteger(value.iteration) ||
    !RUBRIC_RESULTS.has(value.result as RubricResult) ||
    typeof value.explanation !== "string"
  ) {
    return null;
  }
  const binding = candidateBinding(value.candidate_version, value.candidate_id);
  const decodedCriteria = criteria(value.criteria);
  if (binding === null || decodedCriteria === null) return null;
  return {
    eventId: value.event_id,
    gradingRunId: value.grading_run_id,
    iteration: value.iteration,
    ...binding,
    result: value.result as RubricResult,
    explanation: value.explanation,
    criteria: decodedCriteria,
  };
}

function feedbackRecord(value: unknown): FeedbackRecord | null {
  if (
    !isObject(value) ||
    !isNonEmptyString(value.event_id) ||
    !isNonEmptyString(value.grading_run_id) ||
    !isNonNegativeInteger(value.iteration) ||
    typeof value.message !== "string"
  ) {
    return null;
  }
  const binding = candidateBinding(value.candidate_version, value.candidate_id);
  if (binding === null) return null;
  return {
    eventId: value.event_id,
    gradingRunId: value.grading_run_id,
    iteration: value.iteration,
    ...binding,
    message: value.message,
  };
}

function decodeArray<T>(
  value: unknown,
  decoder: (item: unknown) => T | null,
): T[] | null {
  if (!Array.isArray(value)) return null;
  const decoded = value.map(decoder);
  return decoded.every((item): item is T => item !== null) ? decoded : null;
}

function recordsMatchCandidates(report: RunReport): boolean {
  const versions = report.candidates.map((candidate) => candidate.version);
  if (new Set(versions).size !== versions.length) return false;
  const eventIds = [
    ...report.evidence.map((item) => item.eventId),
    ...report.evaluations.map((item) => item.eventId),
    ...report.feedback.map((item) => item.eventId),
  ];
  if (new Set(eventIds).size !== eventIds.length) return false;
  const candidates = new Map(
    report.candidates.map((candidate) => [candidate.version, candidate.candidateId]),
  );
  if (
    report.candidates.some(
      (candidate) => candidate.gradingRunId !== report.gradingRunId,
    ) ||
    report.evidence.some(
      (item) =>
        item.gradingRunId !== report.gradingRunId ||
        !evidenceMatchesCandidate(item, item.candidateId) ||
        candidates.get(item.candidateVersion) !== item.candidateId,
    )
  ) {
    return false;
  }
  return [...report.evaluations, ...report.feedback].every(
    (item) =>
      item.gradingRunId === report.gradingRunId &&
      (item.candidateVersion === null ||
        candidates.get(item.candidateVersion) === item.candidateId),
  );
}

function decodeWireRunReport(value: Record<string, unknown>): RunReport | null {
  if (
    (value.mode !== "demo" && value.mode !== "live") ||
    !isNonEmptyString(value.thread_id) ||
    !isNonEmptyString(value.inner_thread_id) ||
    !isNonEmptyString(value.grading_run_id) ||
    !TERMINAL_STATUSES.has(value.terminal_status as TerminalStatus) ||
    typeof value.accepted !== "boolean" ||
    !GATE_REASONS.has(value.gate_reason as GateReason) ||
    !isNonNegativeInteger(value.iterations) ||
    (value.final_candidate !== null && typeof value.final_candidate !== "string")
  ) {
    return null;
  }
  const candidates = decodeArray(value.candidates, candidateRecord);
  const evidence = decodeArray(value.evidence, evidenceRecord);
  const evaluations = decodeArray(value.evaluations, evaluationRecord);
  const feedback = decodeArray(value.feedback, feedbackRecord);
  if (
    candidates === null ||
    evidence === null ||
    evaluations === null ||
    feedback === null
  ) {
    return null;
  }
  const report: RunReport = {
    mode: value.mode,
    threadId: value.thread_id,
    innerThreadId: value.inner_thread_id,
    gradingRunId: value.grading_run_id,
    terminalStatus: value.terminal_status as TerminalStatus,
    accepted: value.accepted,
    gateReason: value.gate_reason as GateReason,
    iterations: value.iterations,
    candidates,
    finalCandidate: value.final_candidate as string | null,
    evidence,
    evaluations,
    feedback,
  };
  return recordsMatchCandidates(report) ? report : null;
}

function normalizedReportToWire(value: Record<string, unknown>): Record<string, unknown> {
  const candidates = Array.isArray(value.candidates)
    ? value.candidates.map((item) =>
        isObject(item)
          ? {
              grading_run_id: item.gradingRunId,
              version: item.version,
              iteration: item.iteration,
              candidate_id: item.candidateId,
              source: item.source,
              source_omitted: item.sourceOmitted ?? false,
            }
          : item,
      )
    : value.candidates;
  const evidence = Array.isArray(value.evidence)
    ? value.evidence.map((item) =>
        isObject(item)
          ? {
              event_id: item.eventId,
              grading_run_id: item.gradingRunId,
              iteration: item.iteration,
              candidate_version: item.candidateVersion,
              candidate_id: item.candidateId,
              requested_candidate_id: item.requestedCandidateId,
              ok: item.ok,
              behavior_failures: item.behaviorFailures,
              profile_failures: item.profileFailures,
              duration_ms: item.durationMs,
              timed_out: item.timedOut,
              output_truncated: item.outputTruncated,
            }
          : item,
      )
    : value.evidence;
  const evaluations = Array.isArray(value.evaluations)
    ? value.evaluations.map((item) =>
        isObject(item)
          ? {
              event_id: item.eventId,
              grading_run_id: item.gradingRunId,
              iteration: item.iteration,
              candidate_version: item.candidateVersion,
              candidate_id: item.candidateId,
              result: item.result,
              explanation: item.explanation,
              criteria: item.criteria,
            }
          : item,
      )
    : value.evaluations;
  const feedback = Array.isArray(value.feedback)
    ? value.feedback.map((item) =>
        isObject(item)
          ? {
              event_id: item.eventId,
              grading_run_id: item.gradingRunId,
              iteration: item.iteration,
              candidate_version: item.candidateVersion,
              candidate_id: item.candidateId,
              message: item.message,
            }
          : item,
      )
    : value.feedback;
  return {
    mode: value.mode,
    thread_id: value.threadId,
    inner_thread_id: value.innerThreadId,
    grading_run_id: value.gradingRunId,
    terminal_status: value.terminalStatus,
    accepted: value.accepted,
    gate_reason: value.gateReason,
    iterations: value.iterations,
    candidates,
    final_candidate: value.finalCandidate,
    evidence,
    evaluations,
    feedback,
  };
}

export function decodeRunReport(value: unknown): RunReport | null {
  if (!isObject(value)) return null;
  return decodeWireRunReport(
    "grading_run_id" in value ? value : normalizedReportToWire(value),
  );
}
