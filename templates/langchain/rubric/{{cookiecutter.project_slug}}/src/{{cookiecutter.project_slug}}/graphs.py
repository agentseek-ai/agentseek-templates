from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, TypedDict, cast

from langchain.agents import create_agent
from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from .contracts import (
    BASELINE_RUBRIC,
    DEFAULT_MAX_ITERATIONS,
    TASK_PROMPT,
    CandidateRecord,
    CandidateTooLongError,
    EvaluationEvent,
    FeedbackRecord,
    PublicError,
    RunMode,
    RunReport,
    TerminalStatus,
    UIEvent,
    UIEventType,
    build_run_report,
    make_public_error,
    normalize_candidate_source,
    validate_run_input,
)
from .demo_models import build_demo_models
from .evidence import RunEvidenceLedger, make_run_test_suite
from .models import LiveConfigurationError, build_live_models, resolve_live_config
from .safe_rubric import SafeRubricMiddleware

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"satisfied", "max_iterations_reached", "failed", "grader_error"})
_EVALUATION_RESULTS = _TERMINAL_STATUSES | {"needs_revision"}
_LIVE_PROVIDERS = frozenset({"openai", "anthropic", "google"})
_SAFE_RUNTIME_ERROR_TYPES = frozenset(
    {"ConnectionError", "RuntimeError", "SafeModelError", "TimeoutError", "TypeError", "ValueError"}
)
_SECRET_VARIABLES = (
    "OPENAI_API_KEY",
    "OPENAI_API_BASE",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_API_URL",
    "GOOGLE_API_KEY",
    "GOOGLE_API_BASE",
    "LANGSMITH_API_KEY",
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(authorization|api[-_ ]?key)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)\bbearer\s+[^\s,;]+"),
    re.compile(r"\b(?:sk|sk-ant)-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{12,}\b"),
)
_MAX_PUBLIC_TEXT = 1200
_MAX_GAP_TEXT = 600


class ApplicationState(TypedDict, total=False):
    request: dict[str, object]
    report: RunReport
    error: PublicError


class CandidateTrackingMiddleware(AgentMiddleware):
    """Record each Worker response against the active zero-based rubric iteration."""

    def __init__(self, ledger: RunEvidenceLedger) -> None:
        self._ledger = ledger

    def _record(self, response: ModelResponse[Any] | AIMessage, request: ModelRequest[Any]) -> None:
        messages = [response] if isinstance(response, AIMessage) else response.result
        candidate = next((message for message in reversed(messages) if isinstance(message, AIMessage)), None)
        if candidate is None:
            return
        iteration = request.state.get("_rubric_iterations", 0) or 0
        self._ledger.record_candidate(normalize_candidate_source(candidate), iteration)

    def wrap_model_call(self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], Any]):
        response = handler(request)
        self._record(response, request)
        return response

    async def awrap_model_call(self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], Any]):
        response = await handler(request)
        self._record(response, request)
        return response


def build_inner_agent(
    *,
    worker_model: BaseChatModel,
    grader_model: BaseChatModel,
    max_iterations: int,
    checkpointer: BaseCheckpointSaver,
    ledger: RunEvidenceLedger,
):
    if max_iterations < 1:
        raise ValueError("max_iterations must be a positive integer")
    return create_agent(
        model=worker_model,
        tools=[],
        middleware=[
            CandidateTrackingMiddleware(ledger),
            SafeRubricMiddleware(
                model=grader_model,
                tools=[make_run_test_suite(ledger)],
                max_iterations=max_iterations,
            ),
        ],
        checkpointer=checkpointer,
    )


def _event_id(
    grading_run_id: str,
    event_type: UIEventType,
    iteration: int,
    candidate_version: int | None,
    sequence: int,
) -> str:
    version = "none" if candidate_version is None else str(candidate_version)
    return f"{grading_run_id}:{event_type}:{iteration}:{version}:{sequence}"


def _sanitize_text(value: object, *, limit: int = _MAX_PUBLIC_TEXT) -> str:
    text = value if isinstance(value, str) else ""
    for variable in _SECRET_VARIABLES:
        secret = os.environ.get(variable)
        if secret:
            text = text.replace(secret, "[REDACTED]")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text[:limit]


def _candidate_for_iteration(
    candidates: Sequence[CandidateRecord],
    iteration: int,
) -> CandidateRecord | None:
    return next((candidate for candidate in reversed(candidates) if candidate["iteration"] == iteration), None)


@dataclass(slots=True)
class _RunContext:
    grading_run_id: str
    ledger: RunEvidenceLedger
    writer: Callable[[dict[str, object]], None]
    sequences: dict[UIEventType, int] = field(default_factory=lambda: defaultdict(int))
    events: list[UIEvent] = field(default_factory=list)
    candidate_count: int = 0
    evidence_count: int = 0
    feedback_message_ids: set[str] = field(default_factory=set)

    def emit(
        self,
        event_type: UIEventType,
        *,
        iteration: int,
        candidate: CandidateRecord | None,
        payload: dict[str, object],
    ) -> UIEvent:
        sequence = self.sequences[event_type]
        self.sequences[event_type] = sequence + 1
        event: UIEvent = {
            "event_id": _event_id(
                self.grading_run_id,
                event_type,
                iteration,
                candidate["version"] if candidate is not None else None,
                sequence,
            ),
            "type": event_type,
            "grading_run_id": self.grading_run_id,
            "iteration": iteration,
            "candidate_version": candidate["version"] if candidate is not None else None,
            "candidate_id": candidate["candidate_id"] if candidate is not None else None,
            "payload": payload,
        }
        self.events.append(event)
        self.writer(cast(dict[str, object], event))
        return event


def _emit_new_candidates(context: _RunContext) -> None:
    while context.candidate_count < len(context.ledger.candidates):
        candidate = context.ledger.candidates[context.candidate_count]
        payload: dict[str, object] = {"source": candidate["source"]}
        if candidate.get("source_omitted") is True:
            payload["source_omitted"] = True
        context.emit(
            "candidate",
            iteration=candidate["iteration"],
            candidate=candidate,
            payload=payload,
        )
        context.candidate_count += 1


def _evidence_payload(record: Mapping[str, object]) -> dict[str, object]:
    return {
        "requested_candidate_id": str(record.get("requested_candidate_id", "")),
        "ok": record.get("ok") is True,
        "behavior_failures": [
            _sanitize_text(item, limit=_MAX_GAP_TEXT)
            for item in record.get("behavior_failures", [])
            if isinstance(item, str)
        ],
        "profile_failures": [
            _sanitize_text(item, limit=_MAX_GAP_TEXT)
            for item in record.get("profile_failures", [])
            if isinstance(item, str)
        ],
        "duration_ms": record.get("duration_ms") if type(record.get("duration_ms")) is int else 0,
        "timed_out": record.get("timed_out") is True,
        "output_truncated": record.get("output_truncated") is True,
    }


def _emit_new_evidence(context: _RunContext) -> None:
    while context.evidence_count < len(context.ledger.evidence):
        record = context.ledger.evidence[context.evidence_count]
        candidate = next(
            (
                item
                for item in context.ledger.candidates
                if item["version"] == record["candidate_version"] and item["candidate_id"] == record["candidate_id"]
            ),
            None,
        )
        context.emit(
            "rubric_evidence",
            iteration=record["iteration"],
            candidate=candidate,
            payload=_evidence_payload(record),
        )
        context.evidence_count += 1


def _criterion_payload(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    criteria: list[dict[str, object]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        criteria.append(
            {
                "criterion": _sanitize_text(raw.get("criterion", raw.get("name", ""))),
                "passed": raw.get("passed") is True,
                "gap": _sanitize_text(raw.get("gap", ""), limit=_MAX_GAP_TEXT),
            }
        )
    return criteria


def _evaluation_payload(value: Mapping[str, object]) -> dict[str, object]:
    result = value.get("result")
    return {
        "result": result if result in _EVALUATION_RESULTS else "grader_error",
        "explanation": _sanitize_text(value.get("explanation", "")),
        "criteria": _criterion_payload(value.get("criteria", [])),
    }


def normalize_inner_chunk(
    stream_mode: str,
    chunk: object,
    context: _RunContext,
) -> None:
    """Translate the pinned inner stream into the sole public event envelope."""
    _emit_new_candidates(context)
    _emit_new_evidence(context)
    if stream_mode == "custom" and isinstance(chunk, Mapping):
        event_type = chunk.get("type")
        if event_type in {"rubric_evaluation_start", "rubric_evaluation_end"}:
            iteration_value = chunk.get("iteration")
            iteration = iteration_value if type(iteration_value) is int and iteration_value >= 0 else 0
            candidate = _candidate_for_iteration(context.ledger.candidates, iteration)
            payload = {} if event_type == "rubric_evaluation_start" else _evaluation_payload(chunk)
            context.emit(
                cast(UIEventType, event_type),
                iteration=iteration,
                candidate=candidate,
                payload=payload,
            )
        return
    if stream_mode != "updates" or not isinstance(chunk, Mapping):
        return
    for update in chunk.values():
        if not isinstance(update, Mapping):
            continue
        messages = update.get("messages", [])
        if not isinstance(messages, Sequence):
            continue
        for message in messages:
            if not (
                isinstance(message, HumanMessage)
                and message.name == "rubric_grader"
                and message.additional_kwargs.get("lc_source") == "rubric_grader"
            ):
                continue
            message_id = message.id or str(id(message))
            if message_id in context.feedback_message_ids:
                continue
            context.feedback_message_ids.add(message_id)
            candidate = context.ledger.current_candidate
            iteration = candidate["iteration"] if candidate is not None else 0
            context.emit(
                "grader_feedback",
                iteration=iteration,
                candidate=candidate,
                payload={"message": _sanitize_text(message.text)},
            )


def _project_evaluations(
    raw_evaluations: object,
    candidates: Sequence[CandidateRecord],
    grading_run_id: str,
    terminal_status: TerminalStatus | None,
) -> list[EvaluationEvent]:
    if not isinstance(raw_evaluations, Sequence):
        return []
    evaluations: list[EvaluationEvent] = []
    raw_items = [item for item in raw_evaluations if isinstance(item, Mapping)]
    for sequence, raw in enumerate(raw_items):
        iteration_value = raw.get("iteration")
        iteration = iteration_value if type(iteration_value) is int and iteration_value >= 0 else sequence
        candidate = _candidate_for_iteration(candidates, iteration)
        payload = _evaluation_payload(raw)
        if sequence == len(raw_items) - 1 and terminal_status not in {None, "satisfied"}:
            payload["result"] = terminal_status
        evaluations.append(
            {
                "event_id": _event_id(
                    grading_run_id,
                    "rubric_evaluation_end",
                    iteration,
                    candidate["version"] if candidate is not None else None,
                    sequence,
                ),
                "grading_run_id": grading_run_id,
                "iteration": iteration,
                "candidate_version": candidate["version"] if candidate is not None else None,
                "candidate_id": candidate["candidate_id"] if candidate is not None else None,
                "result": cast(Any, payload["result"]),
                "explanation": cast(str, payload["explanation"]),
                "criteria": cast(Any, payload["criteria"]),
            }
        )
    return evaluations


def _project_feedback(
    messages: object,
    candidates: Sequence[CandidateRecord],
    grading_run_id: str,
) -> list[FeedbackRecord]:
    if not isinstance(messages, Sequence):
        return []
    feedback_messages = [
        message
        for message in messages
        if isinstance(message, HumanMessage)
        and message.name == "rubric_grader"
        and message.additional_kwargs.get("lc_source") == "rubric_grader"
    ]
    feedback: list[FeedbackRecord] = []
    for sequence, message in enumerate(feedback_messages):
        candidate = candidates[min(sequence, len(candidates) - 1)] if candidates else None
        iteration = candidate["iteration"] if candidate is not None else sequence
        feedback.append(
            {
                "event_id": _event_id(
                    grading_run_id,
                    "grader_feedback",
                    iteration,
                    candidate["version"] if candidate is not None else None,
                    sequence,
                ),
                "grading_run_id": grading_run_id,
                "iteration": iteration,
                "candidate_version": candidate["version"] if candidate is not None else None,
                "candidate_id": candidate["candidate_id"] if candidate is not None else None,
                "message": _sanitize_text(message.text),
            }
        )
    return feedback


def _project_evidence(ledger: RunEvidenceLedger) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for sequence, record in enumerate(ledger.evidence):
        item = dict(record)
        item["event_id"] = _event_id(
            ledger.grading_run_id,
            "rubric_evidence",
            record["iteration"],
            record["candidate_version"],
            sequence,
        )
        item["behavior_failures"] = cast(list[str], _evidence_payload(record)["behavior_failures"])
        item["profile_failures"] = cast(list[str], _evidence_payload(record)["profile_failures"])
        projected.append(item)
    return projected


def _report_events(report: RunReport) -> list[UIEvent]:
    events: list[UIEvent] = []
    for sequence, candidate in enumerate(report["candidates"]):
        payload: dict[str, object] = {"source": candidate["source"]}
        if candidate.get("source_omitted") is True:
            payload["source_omitted"] = True
        events.append(
            {
                "event_id": _event_id(
                    report["grading_run_id"],
                    "candidate",
                    candidate["iteration"],
                    candidate["version"],
                    sequence,
                ),
                "type": "candidate",
                "grading_run_id": report["grading_run_id"],
                "iteration": candidate["iteration"],
                "candidate_version": candidate["version"],
                "candidate_id": candidate["candidate_id"],
                "payload": payload,
            }
        )
    for feedback in report["feedback"]:
        events.append(
            {
                "event_id": feedback["event_id"],
                "type": "grader_feedback",
                "grading_run_id": report["grading_run_id"],
                "iteration": feedback["iteration"],
                "candidate_version": feedback["candidate_version"],
                "candidate_id": feedback["candidate_id"],
                "payload": {"message": feedback["message"]},
            }
        )
    for sequence, evaluation in enumerate(report["evaluations"]):
        start_id = _event_id(
            report["grading_run_id"],
            "rubric_evaluation_start",
            evaluation["iteration"],
            evaluation["candidate_version"],
            sequence,
        )
        events.extend(
            [
                {
                    "event_id": start_id,
                    "type": "rubric_evaluation_start",
                    "grading_run_id": report["grading_run_id"],
                    "iteration": evaluation["iteration"],
                    "candidate_version": evaluation["candidate_version"],
                    "candidate_id": evaluation["candidate_id"],
                    "payload": {},
                },
                {
                    "event_id": evaluation["event_id"],
                    "type": "rubric_evaluation_end",
                    "grading_run_id": report["grading_run_id"],
                    "iteration": evaluation["iteration"],
                    "candidate_version": evaluation["candidate_version"],
                    "candidate_id": evaluation["candidate_id"],
                    "payload": {
                        "result": evaluation["result"],
                        "explanation": evaluation["explanation"],
                        "criteria": cast(list[dict[str, object]], evaluation["criteria"]),
                    },
                },
            ]
        )
    for evidence in report["evidence"]:
        events.append(
            {
                "event_id": evidence["event_id"],
                "type": "rubric_evidence",
                "grading_run_id": report["grading_run_id"],
                "iteration": evidence["iteration"],
                "candidate_version": evidence["candidate_version"],
                "candidate_id": evidence["candidate_id"],
                "payload": _evidence_payload(evidence),
            }
        )
    phase = {
        "candidate": 0,
        "rubric_evaluation_start": 1,
        "rubric_evidence": 2,
        "rubric_evaluation_end": 3,
        "grader_feedback": 4,
    }
    return sorted(events, key=lambda item: (item["iteration"], phase[item["type"]], item["event_id"]))


def reconcile_public_events(events: Sequence[Mapping[str, object]], report: RunReport) -> list[UIEvent]:
    """Replace provisional progress with the deterministic authoritative projection."""
    del events
    return _report_events(report)


def _stream_writer() -> Callable[[dict[str, object]], None]:
    try:
        return get_stream_writer()
    except (KeyError, RuntimeError):
        return lambda _: None


def _outer_thread_id(config: RunnableConfig) -> str:
    configurable = config.get("configurable", {})
    thread_id = configurable.get("thread_id") if isinstance(configurable, Mapping) else None
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise ValueError("A non-empty configurable.thread_id is required")
    return thread_id


def _public_runtime_error() -> PublicError:
    return make_public_error("runtime", "Run failed safely; inspect sanitized server diagnostics.")


def _runtime_provider_context(mode: RunMode, worker: BaseChatModel) -> str:
    provider = getattr(worker, "provider", None)
    return provider if provider in _LIVE_PROVIDERS else mode


def _safe_runtime_error_type(exc: Exception) -> str:
    error_type = type(exc).__name__
    return error_type if error_type in _SAFE_RUNTIME_ERROR_TYPES else "RuntimeError"


def build_application_graph(*, mode: RunMode, model_factory: Callable[[], object]):
    """Build stable outer topology and allocate every runtime dependency per submission."""

    async def run(state: ApplicationState, config: RunnableConfig) -> ApplicationState:
        request = state.get("request", {})
        try:
            if not isinstance(request, Mapping):
                raise ValueError("request must be an object")
            run_input = validate_run_input(request)
            outer_thread_id = _outer_thread_id(config)
            if mode == "demo" and run_input != {
                "rubric": BASELINE_RUBRIC,
                "max_iterations": DEFAULT_MAX_ITERATIONS,
            }:
                raise ValueError("Demo accepts only the baseline rubric and iteration cap")
        except ValueError as exc:
            return {"error": make_public_error("invalid_input", _sanitize_text(str(exc)))}

        try:
            models = model_factory()
        except LiveConfigurationError as exc:
            return {
                "error": make_public_error(
                    "live_configuration",
                    _sanitize_text(str(exc)),
                    missing=exc.missing,
                )
            }
        except Exception:
            return {"error": _public_runtime_error()}

        worker = getattr(models, "worker", None)
        grader = getattr(models, "grader", None)
        if not isinstance(worker, BaseChatModel) or not isinstance(grader, BaseChatModel):
            return {"error": _public_runtime_error()}

        inner_thread_id = str(uuid.uuid4())
        grading_run_id = str(uuid.uuid4())
        ledger = RunEvidenceLedger(grading_run_id=grading_run_id)
        try:
            inner = build_inner_agent(
                worker_model=worker,
                grader_model=grader,
                max_iterations=run_input["max_iterations"],
                checkpointer=InMemorySaver(),
                ledger=ledger,
            )
        except Exception:
            return {"error": _public_runtime_error()}

        inner_config = {"configurable": {"thread_id": inner_thread_id}}
        context = _RunContext(
            grading_run_id=grading_run_id,
            ledger=ledger,
            writer=_stream_writer(),
        )
        inner_stream = inner.astream(
            {"messages": [HumanMessage(TASK_PROMPT)], "rubric": run_input["rubric"]},
            config=inner_config,
            stream_mode=["updates", "custom"],
        )
        try:
            async for stream_mode, chunk in inner_stream:
                normalize_inner_chunk(stream_mode, chunk, context)
        except asyncio.CancelledError:
            raise
        except CandidateTooLongError:
            _emit_new_candidates(context)
            _emit_new_evidence(context)
            candidates = [cast(CandidateRecord, dict(item)) for item in ledger.candidates]
            try:
                checkpoint = dict(inner.get_state(inner_config).values)
                evaluations = _project_evaluations(
                    checkpoint.get("_rubric_evaluations", []),
                    candidates,
                    grading_run_id,
                    None,
                )
                feedback = _project_feedback(checkpoint.get("messages", []), candidates, grading_run_id)
                report = build_run_report(
                    mode=mode,
                    thread_id=outer_thread_id,
                    inner_thread_id=inner_thread_id,
                    grading_run_id=grading_run_id,
                    terminal_status="failed",
                    iterations=candidates[-1]["iteration"] + 1,
                    candidates=candidates,
                    final_candidate=None,
                    evidence=cast(Any, _project_evidence(ledger)),
                    evaluations=evaluations,
                    feedback=feedback,
                )
            except Exception:
                return {"error": _public_runtime_error()}
            return {"report": report}
        except Exception as exc:
            logger.error(
                "Rubric run failed safely (mode=%s, provider=%s, error_type=%s)",
                mode,
                _runtime_provider_context(mode, worker),
                _safe_runtime_error_type(exc),
            )
            return {"error": _public_runtime_error()}
        finally:
            with suppress(Exception):
                await inner_stream.aclose()

        _emit_new_candidates(context)
        _emit_new_evidence(context)
        checkpoint = dict(inner.get_state(inner_config).values)
        raw_status = checkpoint.get("_rubric_status")
        if raw_status not in _TERMINAL_STATUSES:
            return {"error": _public_runtime_error()}
        terminal_status = cast(TerminalStatus, raw_status)
        iterations_value = checkpoint.get("_rubric_iterations")
        iterations = iterations_value if type(iterations_value) is int and iterations_value >= 0 else 0
        messages = checkpoint.get("messages", [])
        final_message = (
            next((message for message in reversed(messages) if isinstance(message, AIMessage)), None)
            if isinstance(messages, Sequence)
            else None
        )
        final_candidate = normalize_candidate_source(final_message) if final_message is not None else None
        candidates = [cast(CandidateRecord, dict(item)) for item in ledger.candidates]
        evaluations = _project_evaluations(
            checkpoint.get("_rubric_evaluations", []),
            candidates,
            grading_run_id,
            terminal_status,
        )
        feedback = _project_feedback(messages, candidates, grading_run_id)
        try:
            report = build_run_report(
                mode=mode,
                thread_id=outer_thread_id,
                inner_thread_id=inner_thread_id,
                grading_run_id=grading_run_id,
                terminal_status=terminal_status,
                iterations=iterations,
                candidates=candidates,
                final_candidate=final_candidate,
                evidence=cast(Any, _project_evidence(ledger)),
                evaluations=evaluations,
                feedback=feedback,
            )
        except (TypeError, ValueError):
            return {"error": _public_runtime_error()}

        final_end = next(
            (event for event in reversed(context.events) if event["type"] == "rubric_evaluation_end"),
            None,
        )
        if final_end is not None and final_end["payload"].get("result") != terminal_status:
            corrected = dict(final_end)
            corrected["payload"] = dict(final_end["payload"])
            corrected["payload"]["result"] = terminal_status
            context.writer(cast(dict[str, object], corrected))
        return {"report": report}

    builder = StateGraph(ApplicationState)
    builder.add_node("run", run)
    builder.add_edge(START, "run")
    builder.add_edge("run", END)
    return builder.compile()


def make_demo_graph():
    return build_application_graph(mode="demo", model_factory=build_demo_models)


def make_live_graph():
    return build_application_graph(
        mode="live",
        model_factory=lambda: build_live_models(resolve_live_config()),
    )
