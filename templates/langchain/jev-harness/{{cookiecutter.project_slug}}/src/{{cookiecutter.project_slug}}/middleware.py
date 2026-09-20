"""Observe the upstream middleware without duplicating its risk decision."""

from typing import Annotated

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain.agents.middleware.types import OmitFromSchema
from langchain_core.messages import ToolMessage
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
    """Keep upstream allow/block behavior and attach UI evidence to ToolMessages.

    The pinned upstream version exposes the probability to its blocked-message
    hook only. Allowed probabilities remain unknown; we do not classify twice
    or infer a score from success. Execution flags are local to each tool call.
    """

    def _blocked_tool_message(self, request, probability):
        result = super()._blocked_tool_message(request, probability)
        result.artifact = {
            "auto_mode": {
                "decision": "blocked",
                "executed": False,
                "risk_probability": probability,
                "threshold": 0.5,
            }
        }
        return result

    @staticmethod
    def _report(result, executed):
        if not isinstance(result, ToolMessage):
            raise TypeError("Harness tools must return ToolMessages.")
        if executed:
            result.artifact = {
                "auto_mode": {
                    "decision": "allowed",
                    "executed": True,
                    "risk_probability": None,
                    "threshold": 0.5,
                }
            }
        return result

    def wrap_tool_call(self, request, handler):
        executed = False

        def observe(req):
            nonlocal executed
            executed = True
            return handler(req)

        return self._report(super().wrap_tool_call(request, observe), executed)

    async def awrap_tool_call(self, request, handler):
        executed = False

        async def observe(req):
            nonlocal executed
            executed = True
            return await handler(req)

        return self._report(await super().awrap_tool_call(request, observe), executed)
