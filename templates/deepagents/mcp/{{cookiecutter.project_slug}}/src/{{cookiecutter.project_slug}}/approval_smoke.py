"""Model-free MCP + local publication approval experiment on Deep Agents 0.7.8."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from .agent import build_graph
from .config import load_mcp_config
from .mcp_smoke import _ensure_calculator_http_server, _first_text_block, run_smoke
from .mcp_tools import load_mcp_tools
from .model import ModelBinding


class PublicationModel(BaseChatModel):
    """Script the model only; real MCP tools and local files perform the work."""
    model_name: str = "course-mcp"
    seen_tools: list[str] = []

    def _get_ls_params(self, stop=None, **kwargs):
        return {"ls_provider": "openai", "ls_model_name": self.model_name, "ls_model_type": "chat"}

    @property
    def _llm_type(self):
        return "course-mcp-scripted"

    def bind_tools(self, tools, **kwargs):
        self.seen_tools = [t.name for t in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if any(m.type == "tool" for m in messages):
            reply = AIMessage(content="Decision applied.")
        else:
            reply = AIMessage(content="", tool_calls=[{
                "name": "publish_calculation", "args": {"a": 37, "b": 58}, "id": "publish",
            }])
        return ChatResult(generations=[ChatGeneration(message=reply)])


async def verify_approval(config_path: Path, output_dir: Path) -> dict:
    config = load_mcp_config(config_path)
    async with _ensure_calculator_http_server(config):
        loaded = await load_mcp_tools(config)
        stdio = next(t for t in loaded.tools if t.name == "calculator_add")
        http = next(t for t in loaded.tools if t.name == "calculator_http_multiply")
        result = {}
        for decision in ("approve", "reject"):
            log = output_dir / f"{decision}.jsonl"
            before = len(log.read_text().splitlines()) if log.exists() else 0

            @tool
            async def publish_calculation(a: int, b: int) -> str:
                """Call real stdio and HTTP calculators and record the result locally after approval."""
                values = {"stdio": _first_text_block(await stdio.ainvoke({"a": a, "b": b})),
                          "http": _first_text_block(await http.ainvoke({"a": a, "b": b}))}
                output_dir.mkdir(parents=True, exist_ok=True)
                with log.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(values) + "\n")
                return json.dumps(values)

            binding = ModelBinding(PublicationModel(), "openai", "course-mcp", "openai:course-mcp")
            graph = build_graph(binding, loaded, checkpointer=InMemorySaver(), extra_tools=[publish_calculation],
                                interrupt_on={"publish_calculation": {"allowed_decisions": ["approve", "reject"]}})
            thread = {"configurable": {"thread_id": decision}}
            paused = await graph.ainvoke({"messages": [{"role": "user", "content": "Publish the test calculation."}]}, thread)
            interrupts = paused.get("__interrupt__")
            if not interrupts or interrupts[0].value["action_requests"][0]["name"] != "publish_calculation":
                raise AssertionError("Missing publication approval interrupt")
            if "task" in binding.model.seen_tools:
                raise AssertionError("The MCP profile must disable the general-purpose subagent")
            current = len(log.read_text().splitlines()) if log.exists() else 0
            if current != before:
                raise AssertionError("Publication executed before approval")
            resumed = await graph.ainvoke(Command(resume={"decisions": [{"type": decision}]}), thread)
            after = len(log.read_text().splitlines()) if log.exists() else 0
            if resumed.get("__interrupt__") or after != before + (decision == "approve"):
                raise AssertionError(f"Unexpected {decision} side effect")
            if decision == "approve" and json.loads(log.read_text().splitlines()[-1]) != {"stdio": "95", "http": "2146"}:
                raise AssertionError("Recorded calculator output is incorrect")
            result[decision] = {"before": before, "after": after}
        return result


async def main() -> None:
    config = Path(".mcp.json")
    smoke = await run_smoke(config)
    with TemporaryDirectory(prefix="mcp-approval-") as tmp:
        result = await verify_approval(config, Path(tmp))
        print(json.dumps({"tools": smoke.tool_names, "approvals": result}))


if __name__ == "__main__":
    asyncio.run(main())
