from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

from {{ cookiecutter.project_slug }} import demo_binding


def test_build_agent_disables_responses_api_for_openai_provider(monkeypatch) -> None:
    registrations = []
    captured = {}

    monkeypatch.setattr(
        demo_binding,
        "register_provider_profile",
        lambda key, profile: registrations.append((key, profile)),
    )

    def fake_create_deep_agent(**kwargs):
        captured.update(kwargs)
        return "agent"

    monkeypatch.setattr(demo_binding, "create_deep_agent", fake_create_deep_agent)
    monkeypatch.setattr(
        demo_binding,
        "get_settings",
        lambda: SimpleNamespace(
            require_model=lambda: "openai:glm-5.2",
            apply_openai_env_bridge=lambda: None,
        ),
    )

    assert demo_binding.build_agent() == "agent"
    assert len(registrations) == 1
    key, profile = registrations[0]
    assert key == "openai"
    assert profile.init_kwargs["use_responses_api"] is False
    assert captured["model"] == "openai:glm-5.2"
    assert captured["tools"] == [demo_binding.outline_answer]


def test_build_agent_uses_chat_completions_with_real_deepagents(monkeypatch) -> None:
    requests = []

    class ChatCompletionsHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers["Content-Length"])
            requests.append((self.path, json.loads(self.rfile.read(length))))
            body = json.dumps(
                {
                    "id": "stub-response",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "test-model",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "stub answer"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), ChatCompletionsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("BUB_MODEL", "openai:test-model")
        monkeypatch.setenv("BUB_API_KEY", "dummy-key")
        monkeypatch.setenv("BUB_API_BASE", f"http://127.0.0.1:{server.server_port}/v1")
        demo_binding.get_settings.cache_clear()

        agent = demo_binding.build_agent()
        result = agent.invoke({"messages": [{"role": "user", "content": "hello"}]})

        assert result["messages"][-1].content == "stub answer"
        assert len(requests) == 1
        path, payload = requests[0]
        assert path == "/v1/chat/completions"
        assert payload["model"] == "test-model"
    finally:
        demo_binding.get_settings.cache_clear()
        server.shutdown()
        thread.join(timeout=5)
