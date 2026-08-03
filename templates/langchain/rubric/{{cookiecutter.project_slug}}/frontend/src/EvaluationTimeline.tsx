import type {
  GraderFeedbackEvent,
  RubricEvaluationEndEvent,
} from "./contracts";
import type { CandidateTimeline, RunTimeline } from "./reportReducer";

type EvaluationTimelineProps = {
  run: RunTimeline | null;
};

function Feedback({ feedback }: { feedback: GraderFeedbackEvent }) {
  return (
    <aside>
      <h4>Grader feedback</h4>
      <p>{feedback.message}</p>
    </aside>
  );
}

function Evaluation({ evaluation }: { evaluation: RubricEvaluationEndEvent }) {
  return (
    <section>
      <h4>Rubric result: {evaluation.result}</h4>
      {evaluation.explanation ? <p>{evaluation.explanation}</p> : null}
      {evaluation.criteria.length > 0 ? (
        <ul>
          {evaluation.criteria.map((criterion, index) => (
            <li key={`${evaluation.eventId}:criterion:${index}`}>
              <span>{criterion.criterion}</span>{" "}
              <strong>{criterion.passed ? "Passed" : "Not passed"}</strong>
              {criterion.gap ? (
                <div>
                  <strong>Gap</strong>
                  <p>{criterion.gap}</p>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function evidenceStatus(candidate: CandidateTimeline): "pending" | "passing" | "failing" {
  if (candidate.evidence.length === 0) return "pending";
  return candidate.evidence.some((event) => event.evidence.ok)
    ? "passing"
    : "failing";
}

function CandidateCard({ timeline }: { timeline: CandidateTimeline }) {
  const { candidate } = timeline;
  return (
    <article aria-labelledby={`candidate-${candidate.version}`}>
      <header>
        <h3 id={`candidate-${candidate.version}`}>
          Candidate v{candidate.version}
        </h3>
        <code title={candidate.candidateId}>{candidate.candidateId.slice(0, 8)}</code>
        <p>Evidence: {evidenceStatus(timeline)}</p>
      </header>
      {candidate.sourceOmitted === true ? (
        <p>Candidate source omitted because it exceeded the 3,500-character limit.</p>
      ) : (
        <pre>
          <code>{candidate.source}</code>
        </pre>
      )}
      {timeline.evidence.map((event) => (
        <section key={event.eventId} aria-label="Structured evidence">
          {event.evidence.behaviorFailures.map((failure, index) => (
            <p key={`${event.eventId}:behavior:${index}`}>{failure}</p>
          ))}
          {event.evidence.profileFailures.map((failure, index) => (
            <p key={`${event.eventId}:profile:${index}`}>{failure}</p>
          ))}
          {event.evidence.timedOut ? <p>Evidence timed out.</p> : null}
          {event.evidence.outputTruncated ? <p>Evidence output was truncated.</p> : null}
        </section>
      ))}
      {timeline.evaluations.map((evaluation) => (
        <Evaluation key={evaluation.eventId} evaluation={evaluation} />
      ))}
      {timeline.feedback.map((feedback) => (
        <Feedback key={feedback.eventId} feedback={feedback} />
      ))}
    </article>
  );
}

export function EvaluationTimeline({ run }: EvaluationTimelineProps) {
  if (run === null) return <p>No evaluation yet.</p>;
  const candidates = Object.values(run.candidatesByVersion).sort(
    (left, right) => left.candidate.version - right.candidate.version,
  );
  const unboundEvaluations = run.unboundEvents.filter(
    (event): event is RubricEvaluationEndEvent =>
      event.type === "rubric_evaluation_end",
  );
  const unboundFeedback = run.unboundEvents.filter(
    (event): event is GraderFeedbackEvent => event.type === "grader_feedback",
  );

  return (
    <section aria-labelledby={`timeline-${run.gradingRunId}`}>
      <h2 id={`timeline-${run.gradingRunId}`}>Evaluation Timeline</h2>
      <p>Grading run: {run.gradingRunId}</p>
      {candidates.map((candidate) => (
        <CandidateCard
          key={`${run.gradingRunId}:${candidate.candidate.version}`}
          timeline={candidate}
        />
      ))}
      {unboundEvaluations.map((evaluation) => (
        <Evaluation key={evaluation.eventId} evaluation={evaluation} />
      ))}
      {unboundFeedback.map((feedback) => (
        <Feedback key={feedback.eventId} feedback={feedback} />
      ))}
    </section>
  );
}
