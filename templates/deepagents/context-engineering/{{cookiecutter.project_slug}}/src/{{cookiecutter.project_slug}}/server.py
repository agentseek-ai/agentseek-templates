"""Same-origin local A/B comparisons with frozen inputs and independent graph state."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections import OrderedDict
from contextlib import aclosing
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

import anyio
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .context import MemoryStore, Settings, fixture_run, validate_reasoning_effort

load_dotenv(interpolate=False)
STATIC = Path(__file__).parent / "static"
MAX_COMPARISONS = 16


class CandidateInput(BaseModel):
    model_id: str = Field(default="", max_length=120)
    reasoning_effort: str = Field(default="", max_length=20)


class CompareInput(BaseModel):
    execution: Literal["fixture", "live"] = "fixture"
    language: Literal["zh", "en"] = "zh"
    prompt: str = Field(min_length=1, max_length=10000)
    material: str = Field(default="", max_length=200000)
    left: CandidateInput = Field(default_factory=CandidateInput)
    right: CandidateInput = Field(default_factory=CandidateInput)


class MemoryInput(BaseModel):
    text: str = Field(max_length=6000)
    approved: bool = False


@dataclass(frozen=True)
class ComparisonSnapshot:
    execution: str
    language: str
    prompt: str
    material: str
    memory: str
    shared: dict


class RunStreamingResponse(StreamingResponse):
    """Close graphs even when a disconnect interrupts sending a yielded packet."""

    def __init__(self, content, cleanup):
        super().__init__(content, media_type="application/x-ndjson")
        self.cleanup = cleanup

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                try:
                    await self.body_iterator.aclose()
                finally:
                    await self.cleanup()


def create_app(*, settings=None, memory_path=None, run_events=None, models_loader=None):
    settings = settings or Settings.from_env()
    memory = MemoryStore(memory_path or Path(".context-lab/memory.json"))
    app = FastAPI(title="Context Lab Compare")
    # Each reserved side owns its run ID; releasing an older request cannot clear a newer run.
    active_runs: dict[tuple[str, str], str] = {}
    # Keep only recent inputs in this local process, never in browser-controlled payloads.
    comparisons: OrderedDict[str, ComparisonSnapshot] = OrderedDict()

    def read_memory():
        try:
            return memory.read()
        except (OSError, ValueError, KeyError, TypeError):
            raise HTTPException(503, "Saved memory is unreadable. Restore it or approve-save a new preference.") from None

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = request.url.hostname
        origin = request.headers.get("origin")
        if host not in ("127.0.0.1", "localhost", "testserver"):
            return JSONResponse({"detail": "Local use only"}, status_code=403)
        if origin and urlsplit(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "Same origin required"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:"
        return response

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/config")
    def configuration():
        return {"provider": settings.provider, "base_url": settings.base_url,
                "models_base_url": settings.models_base_url or settings.base_url,
                "keys_ready": bool(settings.api_key and settings.querit_key), "model_key_ready": bool(settings.api_key),
                "memory": read_memory(), "context_policy": settings.context_policy,
                "tracing_enabled": settings.tracing_enabled}

    @app.get("/api/models")
    async def models():
        if not settings.api_key:
            return {"available": False, "models": [], "manual_allowed": True, "code": "model_key_required"}
        try:
            from .discovery import discover_models
            result = await (models_loader or discover_models)(settings)
            return {"available": True, "provider": settings.provider, "base_url": settings.models_base_url or settings.base_url, "manual_allowed": True, **result}
        except Exception:
            # Unsupported /models is normal on compatible gateways. Never leak raw SDK errors.
            return {"available": False, "models": [], "manual_allowed": True, "code": "discovery_unavailable"}

    @app.put("/api/memory")
    def save_memory(body: MemoryInput):
        try:
            memory.save(body.text, approved=body.approved)
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        return {"saved": True}

    def validate_candidates(execution, candidates):
        try:
            for candidate in candidates:
                validate_reasoning_effort(candidate.reasoning_effort)
                if execution == "live":
                    settings.require_live(candidate.model_id, candidate.reasoning_effort)
        except ValueError as error:
            raise HTTPException(400, str(error)) from None

    def packet(item, compare_id, side=None):
        return json.dumps({**item, "compare_id": compare_id, **({"side": side} if side else {})}, ensure_ascii=False) + "\n"

    def release_run(compare_id, side, run_id):
        if active_runs.get((compare_id, side)) == run_id:
            del active_runs[(compare_id, side)]

    async def side_events(compare_id, side, run_id, candidate, snapshot, *, rerun=False):
        outcome = "incomplete"
        yield {"type": "side_start", "run_id": run_id, "model_id": candidate.model_id,
               "execution": snapshot.execution, "shared": snapshot.shared,
               "effective_options": settings.effective_options(candidate.reasoning_effort)}
        try:
            from .agent import live_events

            if snapshot.execution == "fixture":
                result = fixture_run(snapshot.prompt, snapshot.language, candidate.model_id, snapshot.memory)
                result["context_policy"] = settings.context_policy
                result["effective_options"] = settings.effective_options(candidate.reasoning_effort)
                outcome = "fixture"
                yield {"type": "result", "run_id": run_id, "result": result}
            else:
                metadata = {"compare_id": compare_id, "run_id": run_id, "side": side,
                            "model_id": candidate.model_id, "language": snapshot.language,
                            "execution": snapshot.execution, "rerun": rerun,
                            **{key: value for key, value in snapshot.shared.items() if key.endswith("_sha256")}}
                events = (run_events or live_events)(
                    settings, candidate.model_id, snapshot.prompt, snapshot.language, snapshot.memory, snapshot.material,
                    reasoning_effort=candidate.reasoning_effort, metadata=metadata,
                )
                async with aclosing(events):
                    async for item in events:
                        if item.get("type") == "result":
                            outcome = item["result"].get("status", "complete")
                        yield {**item, "run_id": run_id}
        except asyncio.CancelledError:
            raise
        except Exception:
            outcome = "error"
            yield {"type": "error", "run_id": run_id, "code": "side_run_failed",
                   "message": "This candidate failed; usage may have been incurred."}
        yield {"type": "side_end", "run_id": run_id, "outcome": outcome}

    @app.post("/api/compare")
    async def compare(body: CompareInput):
        if not body.prompt.strip():
            raise HTTPException(400, "Task must not be empty.")
        validate_candidates(body.execution, (body.left, body.right))
        if active_runs:
            raise HTTPException(409, "A comparison is already active.")
        # Freeze memory once for the pair, even if a Save action happens between sides.
        approved_memory = read_memory()
        compare_id = str(uuid4())
        shared = {"language": body.language, "context_policy": settings.context_policy,
                  "memory_sha256": hashlib.sha256(approved_memory.encode("utf-8")).hexdigest(),
                  "prompt_sha256": hashlib.sha256(body.prompt.encode("utf-8")).hexdigest(),
                  "material_sha256": hashlib.sha256(body.material.encode("utf-8")).hexdigest(),
                  "retrieval": "independent_dynamic_search"}
        snapshot = ComparisonSnapshot(body.execution, body.language, body.prompt, body.material, approved_memory, shared)
        comparisons[compare_id] = snapshot
        while len(comparisons) > MAX_COMPARISONS:
            comparisons.popitem(last=False)
        run_ids = {side: str(uuid4()) for side in ("left", "right")}
        active_runs.update({(compare_id, side): run_id for side, run_id in run_ids.items()})
        tasks = []

        async def cleanup():
            for task in tasks:
                if not task.done():
                    task.cancel()
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                for side, run_id in run_ids.items():
                    release_run(compare_id, side, run_id)

        async def stream():
            nonlocal tasks
            queue = asyncio.Queue(maxsize=64)
            outcomes = {"left": "incomplete", "right": "incomplete"}

            async def produce(side):
                try:
                    async with aclosing(side_events(compare_id, side, run_ids[side], getattr(body, side), snapshot)) as events:
                        async for item in events:
                            await queue.put((side, item))
                finally:
                    release_run(compare_id, side, run_ids[side])
                    if not asyncio.current_task().cancelling():
                        await queue.put((side, None))

            try:
                tasks = [asyncio.create_task(produce(side)) for side in ("left", "right")]
                yield packet({"type": "compare_start", "shared": shared}, compare_id)
                pending = 2
                while pending:
                    side, item = await queue.get()
                    if item is None:
                        pending -= 1
                        continue
                    if item["type"] == "side_end":
                        outcomes[side] = item["outcome"]
                    yield packet(item, compare_id, side)
                yield packet({"type": "compare_end", "outcomes": outcomes}, compare_id)
            finally:
                await cleanup()
        return RunStreamingResponse(stream(), cleanup)

    @app.post("/api/compare/{compare_id}/rerun/{side}")
    async def rerun_side(compare_id: str, side: Literal["left", "right"], body: CandidateInput):
        snapshot = comparisons.get(compare_id)
        if snapshot is None:
            raise HTTPException(404, "Comparison unavailable or expired. Start a new comparison.")
        validate_candidates(snapshot.execution, (body,))
        if (compare_id, side) in active_runs:
            raise HTTPException(409, "This candidate is already active.")
        if any(pair_id != compare_id for pair_id, _ in active_runs):
            raise HTTPException(409, "Another comparison is already active.")
        run_id = str(uuid4())
        active_runs[(compare_id, side)] = run_id

        async def cleanup():
            release_run(compare_id, side, run_id)

        async def stream():
            try:
                async with aclosing(side_events(compare_id, side, run_id, body, snapshot, rerun=True)) as events:
                    async for item in events:
                        yield packet(item, compare_id, side)
            finally:
                await cleanup()
        return RunStreamingResponse(stream(), cleanup)

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("CONTEXT_LAB_PORT", "{{ cookiecutter.port }}")))


if __name__ == "__main__":
    main()
