"""Script model replies while keeping DeepAgents and QuickJS execution real."""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr


class ScriptedModel(BaseChatModel):
    replies: list[AIMessage]
    _cursor: int = PrivateAttr(default=0)

    @property
    def _llm_type(self):
        return "template-scripted"

    def _get_ls_params(self, stop=None, **kwargs):
        return {"ls_provider": "openai", "ls_model_name": "template-scripted"}

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        reply = self.replies[self._cursor]
        self._cursor += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])


def call(name, args, call_id):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])
