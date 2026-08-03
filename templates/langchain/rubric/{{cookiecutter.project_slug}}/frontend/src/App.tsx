import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import { useStream } from "@langchain/react";

import { AcceptanceGate } from "./AcceptanceGate";
import {
  BASELINE_RUBRIC,
  DEFAULT_MAX_ITERATIONS,
  MAX_ITERATIONS,
  TASK_PROMPT,
  type RunMode,
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
} from "./reportReducer";

type RunRequest = {
  sessionKey: string;
  mode: RunMode;
  rubric: string;
  maxIterations: number;
};

type ApplicationState = {
  request?: {
    rubric: string;
    max_iterations: number;
  };
  report?: unknown;
  error?: unknown;
};

type PublicError = {
  code: "invalid_input" | "live_configuration" | "runtime";
  message: string;
  missing: string[];
};

type RunSessionProps = {
  mode: RunMode;
  request: RunRequest | null;
  stopping: boolean;
  onEvent: (mode: RunMode, value: unknown) => void;
  onReport: (mode: RunMode, value: unknown) => void;
  onPublicError: (mode: RunMode, value: unknown) => void;
  onTransportError: (mode: RunMode, value: unknown) => void;
  onCancelled: (mode: RunMode) => void;
  onThreadId: (mode: RunMode, threadId: string) => void;
  onStopReady: (stopRun: (() => Promise<void>) | null) => void;
  onRunningChange: (running: boolean) => void;
  onEndedWithoutReport: (mode: RunMode) => void;
};

const PUBLIC_ERROR_CODES = new Set<PublicError["code"]>([
  "invalid_input",
  "live_configuration",
  "runtime",
]);
const SAFE_VARIABLE = /^[A-Z][A-Z0-9_]{0,63}$/;

function decodePublicError(value: unknown): PublicError | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  const candidate = value as Record<string, unknown>;
  if (
    !PUBLIC_ERROR_CODES.has(candidate.code as PublicError["code"]) ||
    typeof candidate.message !== "string" ||
    candidate.message.length === 0 ||
    candidate.message.length > 1200 ||
    !Array.isArray(candidate.missing) ||
    !candidate.missing.every(
      (item) => typeof item === "string" && SAFE_VARIABLE.test(item),
    )
  ) {
    return null;
  }
  return {
    code: candidate.code as PublicError["code"],
    message: candidate.message.replace(/[\u0000-\u001f\u007f]/g, " ").trim(),
    missing: [...candidate.missing] as string[],
  };
}

function publicErrorMessage(error: PublicError): string {
  if (error.code === "live_configuration") {
    return `${error.message} Complete the documented provider setup on the LangGraph server, then run again. Credentials stay server-side.`;
  }
  return error.message;
}

function isCancellation(value: unknown): boolean {
  return (
    typeof value === "object" &&
    value !== null &&
    "name" in value &&
    (value as { name?: unknown }).name === "AbortError"
  );
}

function hasAcceptanceInvariant(report: RunReport): boolean {
  if (report.accepted) {
    return (
      report.terminalStatus === "satisfied" &&
      report.gateReason === "satisfied_with_current_evidence"
    );
  }
  return report.terminalStatus === "satisfied"
    ? report.gateReason === "current_evidence_missing"
    : report.gateReason === "terminal_status_not_satisfied";
}

function RunSession({
  mode,
  request,
  stopping,
  onEvent,
  onReport,
  onPublicError,
  onTransportError,
  onCancelled,
  onThreadId,
  onStopReady,
  onRunningChange,
  onEndedWithoutReport,
}: RunSessionProps) {
  const submitted = useRef(false);
  const sawLoading = useRef(false);
  const handledReport = useRef<unknown>(undefined);
  const handledPublicError = useRef<unknown>(undefined);
  const handledTransportError = useRef<unknown>(undefined);
  const activeMode = request?.mode ?? mode;
  const apiUrl =
    import.meta.env.VITE_LANGGRAPH_API_URL ??
    "http://127.0.0.1:{{ cookiecutter.langgraph_port }}";

  const stream = useStream<ApplicationState>({
    apiUrl,
    assistantId: activeMode === "demo" ? "rubric-demo" : "rubric-live",
    threadId: null,
    onCustomEvent: (value) => onEvent(activeMode, value),
    onThreadId: (threadId) => onThreadId(activeMode, threadId),
  });

  useEffect(() => {
    if (request === null) {
      onStopReady(null);
      return;
    }
    const stopRun = () => stream.stop();
    onStopReady(stopRun);
    return () => onStopReady(null);
  }, [onStopReady, request, stream]);

  useEffect(() => {
    if (request === null || submitted.current) return;
    submitted.current = true;
    onRunningChange(true);
    void Promise.resolve(
      stream.submit({
        request: {
          rubric: request.rubric,
          max_iterations: request.maxIterations,
        },
      }),
    ).catch((error: unknown) => onTransportError(request.mode, error));
  }, [onRunningChange, onTransportError, request, stream]);

  useEffect(() => {
    if (request === null || stopping) return;
    if (
      stream.values.report !== undefined &&
      stream.values.report !== handledReport.current
    ) {
      handledReport.current = stream.values.report;
      onReport(request.mode, stream.values.report);
    }
    if (
      stream.values.error !== undefined &&
      stream.values.error !== handledPublicError.current
    ) {
      handledPublicError.current = stream.values.error;
      onPublicError(request.mode, stream.values.error);
    }
  }, [onPublicError, onReport, request, stopping, stream.values]);

  useEffect(() => {
    if (
      request === null ||
      stopping ||
      stream.error === null ||
      stream.error === undefined ||
      stream.error === handledTransportError.current
    ) {
      return;
    }
    handledTransportError.current = stream.error;
    if (isCancellation(stream.error)) {
      onCancelled(request.mode);
    } else {
      onTransportError(request.mode, stream.error);
    }
  }, [onCancelled, onTransportError, request, stopping, stream.error]);

  useEffect(() => {
    if (request === null || stopping) return;
    if (stream.isLoading) {
      sawLoading.current = true;
      onRunningChange(true);
      return;
    }
    if (
      sawLoading.current &&
      stream.values.report === undefined &&
      stream.values.error === undefined &&
      (stream.error === null || stream.error === undefined)
    ) {
      onRunningChange(false);
      onEndedWithoutReport(request.mode);
    }
  }, [
    onEndedWithoutReport,
    onRunningChange,
    request,
    stopping,
    stream.error,
    stream.isLoading,
    stream.values,
  ]);

  return null;
}

function freshSessionKey(): string {
  return crypto.randomUUID();
}

export default function App() {
  const [mode, setMode] = useState<RunMode>("demo");
  const [rubric, setRubric] = useState(BASELINE_RUBRIC);
  const [maxIterations, setMaxIterations] = useState(DEFAULT_MAX_ITERATIONS);
  const [reportState, dispatch] = useReducer(
    reportReducer,
    undefined,
    createReportState,
  );
  const [request, setRequest] = useState<RunRequest | null>(null);
  const [running, setRunning] = useState(false);
  const [stopping, setStopping] = useState(false);
  const stopRunRef = useRef<(() => Promise<void>) | null>(null);
  const [validationText, setValidationText] = useState<string | null>(null);
  const [statusText, setStatusText] = useState("Ready for a grading run.");
  const [activeRunIds, setActiveRunIds] = useState<
    Record<RunMode, string | null>
  >({ demo: null, live: null });
  const [serverThreadIds, setServerThreadIds] = useState<
    Record<RunMode, string | null>
  >({ demo: null, live: null });
  const [errorsByMode, setErrorsByMode] = useState<
    Record<RunMode, string | null>
  >({ demo: null, live: null });

  const selectedReport = reportState.reportsByMode[mode];
  const selectedRunId = activeRunIds[mode] ?? selectedReport?.gradingRunId ?? null;
  const selectedRun = selectedRunId === null
    ? null
    : reportState.runsById[selectedRunId] ?? null;

  const finishRun = useCallback((finishedMode: RunMode, status: string) => {
    setRunning(false);
    setStopping(false);
    setRequest(null);
    setStatusText(status);
    setErrorsByMode((current) => ({ ...current, [finishedMode]: null }));
  }, []);

  const handleEvent = useCallback((eventMode: RunMode, value: unknown) => {
    const event = decodeUIEvent(value);
    if (event === null) {
      dispatch({ type: "event_received", value });
      return;
    }
    setActiveRunIds((current) => ({
      ...current,
      [eventMode]: event.gradingRunId,
    }));
    dispatch({ type: "event_received", value });
  }, []);

  const handleReport = useCallback((runMode: RunMode, value: unknown) => {
    const decoded = decodeRunReport(value);
    if (
      decoded === null ||
      decoded.mode !== runMode ||
      !hasAcceptanceInvariant(decoded)
    ) {
      setErrorsByMode((current) => ({
        ...current,
        [runMode]: "The server returned an invalid run report. No acceptance decision was recorded.",
      }));
      setRunning(false);
      setStopping(false);
      setRequest(null);
      setStatusText("Run ended without a valid report.");
      return;
    }
    dispatch({ type: "report_received", value });
    setActiveRunIds((current) => ({
      ...current,
      [runMode]: decoded.gradingRunId,
    }));
    finishRun(runMode, "Run complete. The final report is authoritative.");
  }, [finishRun]);

  const handlePublicError = useCallback((runMode: RunMode, value: unknown) => {
    const decoded = decodePublicError(value);
    setErrorsByMode((current) => ({
      ...current,
      [runMode]: decoded === null
        ? "The server returned an invalid error response. No report was created."
        : publicErrorMessage(decoded),
    }));
    setRunning(false);
    setStopping(false);
    setRequest(null);
    setStatusText("Run stopped before a report was created.");
  }, []);

  const handleTransportError = useCallback((runMode: RunMode, value: unknown) => {
    if (isCancellation(value)) {
      setErrorsByMode((current) => ({ ...current, [runMode]: null }));
      setStatusText("Run cancelled. No report was created.");
    } else {
      setErrorsByMode((current) => ({
        ...current,
        [runMode]: "Could not reach the LangGraph server. Check that it is running and try again.",
      }));
      setStatusText("Transport failure. No report was created.");
    }
    setRunning(false);
    setStopping(false);
    setRequest(null);
  }, []);

  const handleCancelled = useCallback((runMode: RunMode) => {
    setErrorsByMode((current) => ({ ...current, [runMode]: null }));
    setRunning(false);
    setStopping(false);
    setRequest(null);
    setStatusText("Run cancelled. No report was created.");
  }, []);

  const handleEndedWithoutReport = useCallback((runMode: RunMode) => {
    setErrorsByMode((current) => ({
      ...current,
      [runMode]: "The stream ended before the server returned a report. Run the grading loop again.",
    }));
    setRunning(false);
    setStopping(false);
    setRequest(null);
    setStatusText("Run ended without a report.");
  }, []);

  const handleThreadId = useCallback((threadMode: RunMode, threadId: string) => {
    setServerThreadIds((current) => ({
      ...current,
      [threadMode]: threadId,
    }));
  }, []);

  const handleStopReady = useCallback(
    (stopRun: (() => Promise<void>) | null) => {
      stopRunRef.current = stopRun;
    },
    [],
  );

  function changeMode(nextMode: RunMode) {
    if (running) return;
    setMode(nextMode);
    setRequest(null);
    setValidationText(null);
    setStopping(false);
    stopRunRef.current = null;
    setStatusText(
      nextMode === "demo"
        ? "Guided Demo is ready. No model key is required."
        : "Live Model is ready when the LangGraph server is configured.",
    );
  }

  function startRun() {
    if (running) return;
    const submittedRubric = mode === "demo" ? BASELINE_RUBRIC : rubric;
    const submittedMaxIterations = mode === "demo"
      ? DEFAULT_MAX_ITERATIONS
      : maxIterations;
    if (!submittedRubric.trim()) {
      setValidationText("Rubric must not be empty.");
      return;
    }
    if (
      !Number.isInteger(submittedMaxIterations) ||
      submittedMaxIterations < 1 ||
      submittedMaxIterations > MAX_ITERATIONS
    ) {
      setValidationText(`Maximum iterations must be from 1 to ${MAX_ITERATIONS}.`);
      return;
    }
    setValidationText(null);
    setErrorsByMode((current) => ({ ...current, [mode]: null }));
    setServerThreadIds((current) => ({ ...current, [mode]: null }));
    setRunning(true);
    setStopping(false);
    setStatusText("Grading loop running");
    setRequest({
      sessionKey: freshSessionKey(),
      mode,
      rubric: submittedRubric,
      maxIterations: submittedMaxIterations,
    });
  }

  function stopRun() {
    const stopCurrentRun = stopRunRef.current;
    if (!running || stopping || stopCurrentRun === null) return;
    setStopping(true);
    setStatusText("Stopping grading loop");
    void stopCurrentRun().then(
      () => handleCancelled(mode),
      (error: unknown) => handleTransportError(mode, error),
    );
  }

  const sessionKey = `${mode}:${request?.sessionKey ?? "idle"}`;
  const modeExplanation = mode === "demo"
    ? "A deterministic, read-only path. It uses the baseline rubric and fixed positive cap so every learner can inspect the same evidence trail without a key."
    : "An editable path using worker and grader models configured only on the LangGraph server. Browser submissions contain the rubric and positive cap only.";
  const hasReport = selectedReport !== null;

  const summary = useMemo(() => {
    if (selectedReport === null) return "No authoritative decision yet";
    return selectedReport.accepted
      ? `Accepted after ${selectedReport.iterations} iteration${selectedReport.iterations === 1 ? "" : "s"}`
      : `Not accepted · ${selectedReport.terminalStatus}`;
  }, [selectedReport]);

  return (
    <main className="app-shell">
      <RunSession
        key={sessionKey}
        mode={mode}
        request={request}
        stopping={stopping}
        onEvent={handleEvent}
        onReport={handleReport}
        onPublicError={handlePublicError}
        onTransportError={handleTransportError}
        onCancelled={handleCancelled}
        onThreadId={handleThreadId}
        onStopReady={handleStopReady}
        onRunningChange={setRunning}
        onEndedWithoutReport={handleEndedWithoutReport}
      />

      <header className="lab-header">
        <div>
          <p className="eyebrow">LangChain learning workbench</p>
          <h1>Rubric Lab</h1>
          <p className="thesis">
            Acceptance is not a score. It is a claim backed by current,
            candidate-bound Evidence.
          </p>
        </div>
        <div className="decision-summary" aria-label="Current decision summary">
          <span>Current path</span>
          <strong>{mode === "demo" ? "Guided Demo" : "Live Model"}</strong>
          <small>{summary}</small>
        </div>
      </header>

      <div className="mode-bar">
        <ModeSwitch mode={mode} disabled={running} onChange={changeMode} />
        <p>{modeExplanation}</p>
      </div>

      <div className="workbench-grid">
        <div className="control-column">
          <section className="task-card" aria-labelledby="fixed-task-title">
            <p className="section-kicker">Fixed teaching task</p>
            <h2 id="fixed-task-title">One task, two grading paths</h2>
            <code>{TASK_PROMPT}</code>
          </section>

          <RubricEditor
            mode={mode}
            rubric={mode === "demo" ? BASELINE_RUBRIC : rubric}
            maxIterations={mode === "demo" ? DEFAULT_MAX_ITERATIONS : maxIterations}
            setRubric={(nextRubric) => {
              if (mode === "live") setRubric(nextRubric);
            }}
            setMaxIterations={(nextMax) => {
              if (mode === "live") setMaxIterations(nextMax);
            }}
            resetBaseline={() => {
              setRubric(BASELINE_RUBRIC);
              setMaxIterations(DEFAULT_MAX_ITERATIONS);
              setValidationText(null);
            }}
            validationText={validationText}
          />

          <section className="run-actions" aria-labelledby="run-action-title">
            <div>
              <p className="section-kicker">Start a fresh grading run</p>
              <h2 id="run-action-title">Follow the evidence</h2>
            </div>
            {mode === "live" ? (
              <p className="boundary-warning">
                <strong>Live Model is not a sandbox.</strong> It sends prompts to
                the configured provider and does not isolate model output, tools,
                files, or network access from this host.
              </p>
            ) : null}
            <div className="action-buttons">
              <button
                type="button"
                className="run-button"
                disabled={running}
                onClick={startRun}
              >
                {hasReport ? "Run again" : "Run grading loop"}
              </button>
              {running ? (
                <button
                  type="button"
                  className="stop-button"
                  disabled={stopping}
                  onClick={stopRun}
                >
                  Stop grading loop
                </button>
              ) : null}
            </div>
            <p className="run-status" aria-live="polite">
              <span className={running ? "status-dot is-running" : "status-dot"} aria-hidden="true" />
              {statusText}
            </p>
            {serverThreadIds[mode] ? (
              <p className="thread-id">Server thread: {serverThreadIds[mode]}</p>
            ) : null}
            {errorsByMode[mode] ? (
              <p className="run-error" role="alert">{errorsByMode[mode]}</p>
            ) : null}
          </section>
        </div>

        <div className="evidence-column">
          <section className="timeline-panel" aria-label="Candidate and evidence history">
            <div className="panel-heading">
              <p className="section-kicker">Evidence rail</p>
              <p>Custom events appear here before the final report arrives.</p>
            </div>
            <EvaluationTimeline run={selectedRun} />
          </section>
          <div className="gate-panel">
            <AcceptanceGate report={selectedReport} />
          </div>
        </div>
      </div>

      {reportState.diagnostic ? (
        <p className="diagnostic" role="status">
          A malformed or replayed stream item was ignored.
        </p>
      ) : null}
    </main>
  );
}
