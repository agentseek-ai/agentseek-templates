"""Normalize OpenAI-compatible tool deltas before the v3 stream bridge."""

from __future__ import annotations

from copy import deepcopy

from langchain_openai import ChatOpenAI


class OpenAICompatibleChatModel(ChatOpenAI):
    """Keep a tool's initial name when a gateway sends empty continuation names.

    SiliconFlow emits ``name=""`` while streaming arguments. LangChain's v3
    compatibility bridge treats that as a replacement name, unlike its legacy
    chunk merger. Normalize it to an absent field at the provider boundary so
    both sync and async streaming retain the name without disabling streaming.
    """

    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        chunk = deepcopy(chunk)
        choices = chunk.get("choices", []) or chunk.get("chunk", {}).get("choices", [])
        for choice in choices:
            for call in (choice.get("delta") or {}).get("tool_calls") or []:
                function = call.get("function") or {}
                if function.get("name") == "":
                    function.pop("name")
        return super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
