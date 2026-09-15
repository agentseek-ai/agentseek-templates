"""Explicit project Memory writes and read-only, server-owned Scope resolution."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, HTTPException
from powercontext.client import PowerContextClient, ServerResponseError
from powercontext.http import (
    CreateScopeRequest,
    ListMemoryEntriesRequest,
    RememberMemoryRequest,
    ResolveScopeBindingRequest,
    ScopeBindingKey,
    SetScopeBindingRequest,
)
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/custom/memory")
TIMEOUT_SECONDS = 3.0


def open_client() -> PowerContextClient:
    return PowerContextClient(
        os.getenv("POWERCONTEXT_URL", "http://127.0.0.1:8000"),
        token=os.getenv("POWERCONTEXT_TOKEN") or None,
        timeout=TIMEOUT_SECONDS,
    )


def project_key() -> ScopeBindingKey:
    return ScopeBindingKey(
        integration="agentseek",
        kind="project",
        external_id=os.getenv("POWERCONTEXT_PROJECT_KEY", "{{ cookiecutter.project_slug }}"),
    )


async def resolve_scope(client: PowerContextClient) -> str:
    scope = await client.resolve_scope_binding(
        ResolveScopeBindingRequest(
            explicit_scope_id=os.getenv("POWERCONTEXT_SCOPE_ID") or None,
            binding_keys=[project_key()],
            allow_default=False,
        )
    )
    return scope.scope_id


@asynccontextmanager
async def memory_client() -> AsyncIterator[PowerContextClient]:
    try:
        async with asyncio.timeout(TIMEOUT_SECONDS), open_client() as client:
            yield client
    except ServerResponseError as exc:
        if exc.status_code == 404:
            raise HTTPException(409, "Create project memory first, or check the configured Scope ID.") from None
        raise HTTPException(
            503, "PowerContext rejected the request. Check the server and backend configuration."
        ) from None
    except Exception:
        # Provider errors can contain credentials or request bodies. Never forward them to the browser.
        raise HTTPException(503, "PowerContext is unavailable. The memory operation was not confirmed.") from None


class MemoryWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=2000)


@router.post("/initialize")
async def initialize_memory() -> dict[str, str]:
    """Create one idempotent project Scope only on an explicit user action."""
    async with memory_client() as client:
        try:
            scope_id = await resolve_scope(client)
        except ServerResponseError as exc:
            if exc.status_code != 404 or os.getenv("POWERCONTEXT_SCOPE_ID"):
                raise
            key = project_key()
            scope = await client.create_scope(
                CreateScopeRequest(
                    title=key.external_id,
                    summary="Project decisions for the AgentSeek PowerContext showcase.",
                    idempotency_key=f"agentseek:{key.external_id}",
                )
            )
            scope_id = scope.scope_id
            await client.set_scope_binding(
                SetScopeBindingRequest.model_validate(
                    {
                        "key": key.model_dump(),
                        "scope_id": scope_id,
                    }
                )
            )
    return {"scope_id": scope_id}


@router.get("")
async def list_memory() -> dict:
    async with memory_client() as client:
        scope_id = await resolve_scope(client)
        result = await client.list_memory_entries(ListMemoryEntriesRequest(scope_id=scope_id))
    return {"scope_id": scope_id, **result.model_dump(mode="json")}


@router.post("")
async def remember_memory(request: MemoryWrite) -> dict:
    async with memory_client() as client:
        scope_id = await resolve_scope(client)
        result = await client.remember_memory(
            RememberMemoryRequest(
                scope_id=scope_id,
                kind="project-decision",
                text=request.text,
                reason="Explicitly saved by the user in the project Memory panel.",
            )
        )
    return result.model_dump(mode="json")
