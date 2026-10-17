"""Same-origin local A/B comparisons with frozen inputs and independent graph state."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .context import CONTEXT_POLICY, MemoryStore, Settings, fixture_run, validate_reasoning_effort

load_dotenv(interpolate=False)
STATIC = Path(__file__).parent / "static"


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


def create_app(*, settings=None, memory_path=None, run_events=None, models_loader=None):
    settings = settings or Settings.from_env()
    memory = MemoryStore(memory_path or Path(".context-lab/memory.json"))
    app = FastAPI(title="Context Lab Compare")
    lock = asyncio.Lock()

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
                "memory": read_memory(), "context_policy": dict(CONTEXT_POLICY),
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

    @app.post("/api/compare")
    async def compare(body: CompareInput):
        if not body.prompt.strip():
            raise HTTPException(400, "Task must not be empty.")
        try:
            for candidate in (body.left, body.right):
                validate_reasoning_effort(candidate.reasoning_effort)
                if body.execution == "live":
                    settings.require_live(candidate.model_id, candidate.reasoning_effort)
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        if lock.locked():
            raise HTTPException(409, "A comparison is already active.")
        # Freeze memory once for the pair, even if a Save action happens between sides.
        snapshot = read_memory()
        await lock.acquire()
        compare_id = str(uuid4())
        shared = {"language": body.language, "context_policy": dict(CONTEXT_POLICY),
                  "memory_sha256": hashlib.sha256(snapshot.encode("utf-8")).hexdigest(),
                  "prompt_sha256": hashlib.sha256(body.prompt.encode("utf-8")).hexdigest(),
                  "material_sha256": hashlib.sha256(body.material.encode("utf-8")).hexdigest(),
                  "retrieval": "independent_dynamic_search"}

        async def stream():
            def packet(item, side=None):
                return json.dumps({"compare_id": compare_id, **({"side": side} if side else {}), **item}, ensure_ascii=False) + "\n"

            outcomes = {}
            try:
                from .agent import live_events
                yield packet({"type": "compare_start", "shared": shared})
                for side in ("left", "right"):
                    candidate = getattr(body, side)
                    yield packet({"type": "side_start", "model_id": candidate.model_id}, side)
                    try:
                        if body.execution == "fixture":
                            result = fixture_run(body.prompt, body.language, candidate.model_id, snapshot)
                            result["context_policy"] = dict(CONTEXT_POLICY)
                            result["effective_options"] = settings.effective_options(candidate.reasoning_effort)
                            outcomes[side] = "fixture"
                            yield packet({"type": "result", "result": result}, side)
                        else:
                            metadata = {"compare_id": compare_id, "side": side,
                                        "model_id": candidate.model_id, "language": body.language}
                            async for item in (run_events or live_events)(
                                settings, candidate.model_id, body.prompt, body.language, snapshot, body.material,
                                reasoning_effort=candidate.reasoning_effort, metadata=metadata,
                            ):
                                if item.get("type") == "result":
                                    outcomes[side] = item["result"].get("status", "complete")
                                yield packet(item, side)
                            outcomes.setdefault(side, "incomplete")
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        outcomes[side] = "error"
                        yield packet({"type": "error", "code": "side_run_failed",
                                      "message": "This candidate failed; usage may have been incurred. The other side continues."}, side)
                yield packet({"type": "compare_end", "outcomes": outcomes})
            finally:
                lock.release()
        return StreamingResponse(stream(), media_type="application/x-ndjson")

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
