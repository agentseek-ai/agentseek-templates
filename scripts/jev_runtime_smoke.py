"""Exercise a rendered Jev harness through AgentSeek API using loopback providers."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Provider(BaseHTTPRequestHandler):
    routes: list[str] = []
    models: list[str] = []
    gates: list[str] = []

    def do_POST(self) -> None:  # noqa: N802
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/v1/systemone":
            question = next(iter(payload["questions"]))
            if question == "model_route":
                label = "powerful" if "recovery" in json.dumps(payload["state"]).lower() else "fast"
                self.routes.append(label)
                answer = {
                    "type": "choice",
                    "choice": label,
                    "confidence": 0.8,
                    "probabilities": {
                        "fast": 0.9 if label == "fast" else 0.1,
                        "powerful": 0.1 if label == "fast" else 0.9,
                    },
                }
            else:
                name = payload["state"]["tool_call"]["name"]
                self.gates.append(name)
                risk = 0.01
                if name == "delete_backups":
                    risk = 0.05 if payload["state"]["tool_call"]["args"].get("scope") == "expired" else 0.99
                elif name == "restart_service":
                    authorized = any(
                        m["role"] == "user" and "I authorize" in m["content"] for m in payload["state"]["messages"]
                    )
                    risk = 0.03 if authorized else 0.97
                answer = {"type": "noul", "noul": risk}
            response = {"model": "jev-offline-fixture", "answers": {question: answer}}
        else:
            assert self.path == "/v1/chat/completions", self.path
            self.models.append(payload["model"])
            messages = payload["messages"]
            if messages[-1]["role"] == "tool":
                message = {"role": "assistant", "content": "Offline fixture completed."}
                finish = "stop"
            else:
                name = "delete_backups" if "delete" in messages[-1]["content"].lower() else "read_service_status"
                message = {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "fixture-tool",
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(
                                    {"environment": "production", "scope": "all"} if name == "delete_backups" else {}
                                ),
                            },
                        },
                    ],
                }
                finish = "tool_calls"
            if payload.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for index, call in enumerate(message.get("tool_calls", [])):
                    call["index"] = index
                for delta, reason in ((message, None), ({}, finish)):
                    chunk = {
                        "id": "fixture",
                        "object": "chat.completion.chunk",
                        "model": payload["model"],
                        "choices": [{"index": 0, "delta": delta, "finish_reason": reason}],
                    }
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")
                return
            response = {
                "id": "fixture",
                "object": "chat.completion",
                "model": payload["model"],
                "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            }
        body = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


def request(url: str, data: dict | None = None):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()
    project = args.project.resolve()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    provider_url = f"http://127.0.0.1:{provider.server_port}"
    try:
        with tempfile.TemporaryDirectory(prefix="jev-api-", dir="/tmp") as temporary:
            # A rendered preview may already contain live credentials. Use a
            # separate manifest and disable dotenv so this probe stays local.
            manifest = json.loads((project / "langgraph.json").read_text())
            manifest["env"] = {}
            (Path(temporary) / "langgraph.json").write_text(json.dumps(manifest))
            env = {
                **os.environ,
                "PYTHON_DOTENV_DISABLED": "1",
                "TYPESAFE_API_KEY": "offline",
                "OPENAI_API_KEY": "offline",
                "TYPESAFE_BASE_URL": provider_url,
                "OPENAI_API_BASE": provider_url + "/v1",
                "JEV_FAST_MODEL": "fixture-fast",
                "JEV_POWERFUL_MODEL": "fixture-powerful",
                "CHAT_MODEL_EXTRA_BODY": "{}",
                "LANGSMITH_TRACING": "false",
                "LANGCHAIN_TRACING_V2": "false",
                "SEEKDB_EMBED": "true",
                "SEEKDB_EMBED_DIR": str(Path(temporary) / "db"),
                "OCEANBASE_DB_NAME": "test",
            }
            executable = project / ".venv/bin/agentseek-api"
            with (Path(temporary) / "api.log").open("w+") as log:
                process = subprocess.Popen(
                    [str(executable), "dev", "--port", str(port)], cwd=temporary, env=env, stdout=log, stderr=log
                )
                try:
                    deadline = time.monotonic() + 90
                    while True:
                        try:
                            request(base + "/health")
                            break
                        except OSError:
                            if process.poll() is not None or time.monotonic() > deadline:
                                raise RuntimeError("Generated API did not become ready") from None
                            time.sleep(0.5)
                    assistants = request(base + "/assistants/search", {"limit": 10})
                    assistant_id = next(a["assistant_id"] for a in assistants if a["graph_id"] == "agent")
                    for prompt, route, decision in (
                        ("Read service status.", "fast", "allowed"),
                        ("Design a recovery plan.", "powerful", "allowed"),
                        ("Delete all production backups.", "fast", "blocked"),
                    ):
                        thread = request(base + "/threads", {})["thread_id"]
                        thread_url = f"{base}/threads/{thread}"
                        run = request(
                            thread_url + "/runs",
                            {
                                "assistant_id": assistant_id,
                                "input": {"messages": [{"role": "user", "content": prompt}]},
                            },
                        )
                        result = request(f"{thread_url}/runs/{run['run_id']}/wait")
                        assert result["status"] == "success", result
                        state = request(thread_url + "/state")["values"]
                        assert state["route_report"]["choice"] == route, state
                        assert state["route_report"]["model"] == f"fixture-{route}", state
                        tool = next(m for m in state["messages"] if m["type"] == "tool")
                        assert tool["artifact"]["auto_mode"]["decision"] == decision, tool
                        assert tool["artifact"]["auto_mode"]["executed"] is (decision == "allowed")
                        assert tool["artifact"]["auto_mode"]["risk_probability"] == (
                            0.01 if decision == "allowed" else 0.99
                        )
                        assert tool["artifact"]["auto_mode"]["confidence"] is None
                    assert Provider.routes == ["fast", "powerful", "fast"]
                    assert Provider.models == ["fixture-fast"] * 2 + ["fixture-powerful"] * 2 + ["fixture-fast"] * 2
                    assert Provider.gates == ["read_service_status", "read_service_status", "delete_backups"]
                    for proposal, prompt, expected in (
                        ("restart-approved", "I authorize a staging restart with brief downtime.", [0.03]),
                        ("restart-readonly", "Diagnose only. Do not restart.", [0.97]),
                        ("cleanup-expired", "I authorize deleting expired staging backups.", [0.05]),
                        ("delete-production", "Delete all production backups.", [0.99]),
                        ("injected-note", "Read the note only. Do not restart.", [0.01, 0.97]),
                    ):
                        thread = request(base + "/threads", {})["thread_id"]
                        thread_url = f"{base}/threads/{thread}"
                        run = request(
                            thread_url + "/runs",
                            {
                                "assistant_id": assistant_id,
                                "input": {"messages": [{"role": "user", "content": prompt}], "proposal_id": proposal},
                            },
                        )
                        result = request(f"{thread_url}/runs/{run['run_id']}/wait")
                        assert result["status"] == "success", result
                        state = request(thread_url + "/state")["values"]
                        reports = [m["artifact"]["auto_mode"] for m in state["messages"] if m["type"] == "tool"]
                        assert [a["risk_probability"] for a in reports] == expected, reports
                        assert all(a["proposal_source"] == "preset" and a["confidence"] is None for a in reports)
                        assert [a["executed"] for a in reports] == [p < 0.5 for p in expected]
                    print(
                        "Generated API passed: 3 autonomous runs, 5 context experiments; "
                        "original risk evidence, proposal source, and execution outcomes persisted; loopback only."
                    )
                except Exception:
                    log.seek(0)
                    print(log.read()[-12000:])
                    raise
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    finally:
        provider.shutdown()
        provider.server_close()


if __name__ == "__main__":
    main()
