from __future__ import annotations

import logging
import re
from typing import Any

from deepagents.middleware import RubricMiddleware
from deepagents.middleware.rubric import ContextT, RubricState
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

_SAFE_ERROR_TYPES = frozenset(
    {
        "AuthenticationError",
        "ConnectionError",
        "GraderError",
        "RateLimitError",
        "RuntimeError",
        "SafeModelError",
        "StructuredOutputValidationError",
        "TimeoutError",
        "TypeError",
        "ValidationError",
        "ValueError",
    }
)


def _safe_error_type(exc: Exception) -> str:
    raw_type = type(exc).__name__
    if raw_type not in _SAFE_ERROR_TYPES:
        return "GraderError"
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", raw_type) is None:
        return "GraderError"
    return raw_type


class SafeRubricMiddleware(RubricMiddleware):
    """Pinned DeepAgents 0.7.1 boundary that only sanitizes grader failures."""

    def _handle_grader_exception(
        self,
        runtime: Runtime[ContextT],
        state: RubricState,
        grading_run_id: str,
        iteration: int,
        exc: Exception,
    ) -> dict[str, Any]:
        error_type = _safe_error_type(exc)
        metadata = self._grader_trace_metadata()
        self._record_grader_trace_metadata(metadata)
        logger.error(
            "Rubric grader failed safely (error_type=%s, effective_strategy=%s)",
            error_type,
            metadata["rubric_grader_effective_strategy"],
        )
        evaluation = {
            "grading_run_id": grading_run_id,
            "iteration": iteration,
            "result": "grader_error",
            "explanation": f"Grader failed with {error_type}; inspect sanitized server diagnostics.",
            "criteria": [],
        }
        self._emit(runtime, "rubric_evaluation_end", grading_run_id, iteration, evaluation)
        if self._on_evaluation is not None:
            try:
                self._on_evaluation(evaluation)
            except Exception as callback_exc:  # noqa: BLE001 - callback failures must not alter grading state
                logger.error(
                    "Rubric evaluation callback failed safely (error_type=%s)",
                    _safe_error_type(callback_exc),
                )
        return {
            "_rubric_evaluations": [*state.get("_rubric_evaluations", []), evaluation],
            "_rubric_iterations": iteration + 1,
            "_rubric_status": "grader_error",
        }
