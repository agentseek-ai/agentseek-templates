"""The configured browser origins must be able to call the API."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    "origin,allowed",
    [("https://smith.langchain.com", True), ("http://localhost:{{ cookiecutter.frontend_port }}", True), ("https://untrusted.example", False)],
)
def test_api_preflight_accepts_studio_and_frontend_only(origin, allowed):
    config = json.loads((Path(__file__).parents[1] / "langgraph.json").read_text())
    app = FastAPI()
    app.add_middleware(CORSMiddleware, **config["http"]["cors"])
    response = TestClient(app).options(
        "/assistants/search",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == (200 if allowed else 400)
    assert response.headers.get("access-control-allow-origin") == (origin if allowed else None)
