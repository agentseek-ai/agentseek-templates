"""Observe the upstream middleware without duplicating its risk decision."""

from contextvars import ContextVar
from typing import Annotated

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain.agents.middleware.types import OmitFromSchema
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableLambda
from langchain_typesafe.experimental.middleware import AutoModeMiddleware
from typing_extensions import NotRequired


class ReportState(AgentState):
    route_report: NotRequired[Annotated[dict, OmitFromSchema(input=True, output=False)]]


class RouteReportMiddleware(AgentMiddleware):
    state_schema = ReportState

    def __init__(self, models):
        self.models = models

    def before_agent(self, state, runtime):
        answer = state["model_route"]
        model = self.models[answer.choice]
        return {
            "route_report": {
                **answer.model_dump(mode="json"),
                "model": getattr(model, "model_name", answer.choice),
            }
        }

    async def abefore_agent(self, state, runtime):
        return self.before_agent(state, runtime)


class ObservedAutoModeMiddleware(AutoModeMiddleware):
    """Observe the SAME classifier response used by the upstream gate.

    The runnable tap does not classify again or replace upstream threshold logic.
    Each tool call owns its response bucket, including parallel async calls.
    Noul returns a probability, not a separate confidence value.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._responses = ContextVar("auto_mode_responses", default=None)
        self.risk_classifier = self.classifier
        self.classifier = self.risk_classifier | RunnableLambda(self._observe_response)

    def _observe_response(self, response):
        bucket = self._responses.get()
        if bucket is not None:
            bucket.append(response)
        return response

    @staticmethod
    def _report(result, executed, responses, request):
        if not isinstance(result, ToolMessage):
            raise TypeError("Harness tools must return ToolMessages.")
        if not responses:
            return result  # Unlisted tools bypass the upstream gate; never label them allowed.
        response = responses[0]
        source = "agent"
        for message in reversed(request.state.get("messages", [])):
            if any(call["id"] == request.tool_call["id"] for call in getattr(message, "tool_calls", [])):
                source = message.additional_kwargs.get("proposal_source", "agent")
                break
        result.artifact = {
            **(result.artifact or {}),
            "auto_mode": {
                "decision": "allowed" if executed else "blocked",
                "executed": executed and result.status != "error",
                "execution_status": "blocked" if not executed else "failed" if result.status == "error" else "completed",
                "risk_probability": response.nouls["is_risky"].noul,
                "confidence": None,
                "threshold": 0.5,
                "arguments": request.tool_call["args"],
                "proposal_source": source,
            }
        }
        return result

    def wrap_tool_call(self, request, handler):
        executed = False

        def observe(req):
            nonlocal executed
            executed = True
            return handler(req)

        responses = []
        token = self._responses.set(responses)
        try:
            result = super().wrap_tool_call(request, observe)
            return self._report(result, executed, responses, request)
        finally:
            self._responses.reset(token)

    async def awrap_tool_call(self, request, handler):
        executed = False

        async def observe(req):
            nonlocal executed
            executed = True
            return await handler(req)

        responses = []
        token = self._responses.set(responses)
        try:
            result = await super().awrap_tool_call(request, observe)
            return self._report(result, executed, responses, request)
        finally:
            self._responses.reset(token)
