from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from deepagents.middleware import GraderResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from pydantic import PrivateAttr

from .contracts import candidate_id, normalize_candidate_source

DEMO_FAILING_SOURCE = """def find_duplicates(values):
    return []
"""

DEMO_PASSING_SOURCE = """def find_duplicates(values):
    seen = []
    duplicates = []
    for value in values:
        if value in seen:
            if value not in duplicates:
                duplicates.append(value)
        else:
            seen.append(value)
    return duplicates
"""

_TRANSCRIPT_RE = re.compile(
    r"<transcript-(?P<nonce>[0-9a-f]+)>\n(?P<body>.*?)\n</transcript-(?P=nonce)>",
    flags=re.DOTALL,
)
_ASSISTANT_RE = re.compile(
    r"(?:\A|\n\n)\[assistant\] (?P<content>.*?)(?=\n\n\[[^]]+\] |\Z)",
    flags=re.DOTALL,
)


def _tool_name(tool: dict[str, Any] | type | BaseTool) -> str:
    name = getattr(tool, "name", None)
    if isinstance(name, str):
        return name
    if isinstance(tool, type):
        return tool.__name__
    function = tool.get("function")
    if isinstance(function, Mapping) and isinstance(function.get("name"), str):
        return function["name"]
    if isinstance(tool.get("name"), str):
        return tool["name"]
    raise TypeError("Bound tool must expose a name.")


def _current_candidate(messages: Sequence[BaseMessage]) -> str:
    payload = next(
        message.text
        for message in reversed(messages)
        if isinstance(message, HumanMessage) and "<transcript-" in message.text
    )
    transcript_match = _TRANSCRIPT_RE.search(payload)
    if transcript_match is None:
        raise ValueError("Grader payload did not contain a transcript.")
    candidates = [match.group("content") for match in _ASSISTANT_RE.finditer(transcript_match.group("body"))]
    if not candidates:
        raise ValueError("Grader transcript did not contain a candidate response.")
    return normalize_candidate_source(candidates[-1])


def _tool_payload(message: ToolMessage) -> dict[str, object]:
    content = message.content
    if isinstance(content, str):
        parsed = json.loads(content)
    elif isinstance(content, list):
        text = "".join(
            item.get("text", "") for item in content if isinstance(item, Mapping) and isinstance(item.get("text"), str)
        )
        parsed = json.loads(text)
    else:
        raise TypeError("Evidence tool output must be JSON text.")
    if not isinstance(parsed, dict):
        raise TypeError("Evidence tool output must be a JSON object.")
    return parsed


class DemoWorkerModel(BaseChatModel):
    """Keyless Worker whose response is derived only from the received transcript."""

    _invocation_count: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "rubric-demo-worker"

    @property
    def invocation_count(self) -> int:
        return self._invocation_count

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        self._invocation_count += 1
        has_feedback = any(
            isinstance(message, HumanMessage)
            and message.name == "rubric_grader"
            and message.additional_kwargs.get("lc_source") == "rubric_grader"
            for message in messages
        )
        source = DEMO_PASSING_SOURCE if has_feedback else DEMO_FAILING_SOURCE
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=source))])


class ScriptedGraderModel(BaseChatModel):
    """Tool-strategy Grader that bases each verdict on just-observed evidence."""

    terminal_result: Literal["failed"] | None = None
    _call_kinds: list[str] = PrivateAttr(default_factory=list)
    _bound_tool_names: set[str] = PrivateAttr(default_factory=set)

    @property
    def _llm_type(self) -> str:
        return "rubric-scripted-grader"

    @property
    def call_kinds(self) -> list[str]:
        return list(self._call_kinds)

    @property
    def bound_tool_names(self) -> set[str]:
        return set(self._bound_tool_names)

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> ScriptedGraderModel:
        del tool_choice, kwargs
        self._bound_tool_names.update(_tool_name(tool) for tool in tools)
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        current_source = _current_candidate(messages)
        evidence_message = next(
            (
                message
                for message in reversed(messages)
                if isinstance(message, ToolMessage) and message.name == "run_test_suite"
            ),
            None,
        )
        if evidence_message is None:
            self._call_kinds.append("request_evidence")
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": f"evidence-{len(self._call_kinds)}",
                        "name": "run_test_suite",
                        "args": {"code": current_source},
                        "type": "tool_call",
                    }
                ],
            )
            return ChatResult(generations=[ChatGeneration(message=message)])

        evidence = _tool_payload(evidence_message)
        current_id = candidate_id(current_source)
        failures = [str(item) for key in ("behavior_failures", "profile_failures") for item in evidence.get(key, [])]
        binding_matches = evidence.get("candidate_id") == current_id and evidence.get(
            "requested_candidate_id"
        ) == evidence.get("candidate_id")
        if not binding_matches and "candidate_binding" not in failures:
            failures.append("candidate_binding")

        if self.terminal_result == "failed":
            result: Literal["satisfied", "needs_revision", "failed"] = "failed"
            explanation = "The rubric cannot be evaluated by this scripted terminal case."
            criteria: list[dict[str, object]] = []
        elif binding_matches and evidence.get("ok") is True:
            result = "satisfied"
            explanation = "The exact current candidate passed the fixed evidence suite."
            criteria = [{"name": "current_candidate_evidence", "passed": True}]
        else:
            result = "needs_revision"
            explanation = "The exact current candidate has failing or mismatched evidence."
            criteria = [
                {
                    "name": failure,
                    "passed": False,
                    "gap": f"Resolve evidence failure: {failure}.",
                }
                for failure in failures or ["evidence_not_passing"]
            ]

        self._call_kinds.append(f"return_{result}")
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": f"verdict-{len(self._call_kinds)}",
                    "name": GraderResponse.__name__,
                    "args": {
                        "result": result,
                        "explanation": explanation,
                        "criteria": criteria,
                    },
                    "type": "tool_call",
                }
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


@dataclass(frozen=True, slots=True)
class DemoModels:
    worker: DemoWorkerModel
    grader: ScriptedGraderModel


def build_demo_models() -> DemoModels:
    """Return an isolated keyless Worker/Grader pair for one Demo run."""
    return DemoModels(
        worker=DemoWorkerModel(),
        grader=ScriptedGraderModel(profile={"structured_output": False}),
    )
