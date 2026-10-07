"""Exercise the generated API stream used by React, with a local scripted provider."""
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
from langgraph_sdk import get_sync_client


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        count = sum(m.get("role") == "tool" for m in payload["messages"])
        message = {"role": "assistant", "content": "Plan checked."}
        if count < 2:
            status = "in_progress" if count == 0 else "completed"
            message = {"role": "assistant", "content": "", "tool_calls": [{
                "id": f"todo-{count}", "type": "function",
                "function": {"name": "write_todos", "arguments": json.dumps({
                    "todos": [{"content": "Check evidence", "status": status}]})},
            }]}
        self.send_response(200)
        if payload.get("stream"):
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            delta = dict(message)
            if "tool_calls" in delta:
                delta["tool_calls"][0]["index"] = 0
            for body in [
                {"id": "course", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                {"id": "course", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls" if count < 2 else "stop"}]},
            ]:
                self.wfile.write(f"data: {json.dumps(body)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
        else:
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"id": "course", "object": "chat.completion", "choices": [{
                "index": 0, "message": message, "finish_reason": "tool_calls" if count < 2 else "stop",
            }]}).encode())


def test_api_stream_delivers_todos_to_frontend(tmp_path):
    root = Path(__file__).resolve().parents[1]
    provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    worker = threading.Thread(target=provider.serve_forever, daemon=True)
    worker.start()
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    env = {**os.environ,
           "OPENAI_API_BASE": f"http://127.0.0.1:{provider.server_port}/v1",
           "SEEKDB_EMBED": "false", "METADATA_DB_BACKEND": "sqlite",
           "METADATA_DB_URL": f"sqlite:///{tmp_path / 'course.db'}",
           "EXECUTOR_BACKEND": "inline", "NO_PROXY": "127.0.0.1,localhost"}
    env_file = tmp_path / ".env"
    env_file.write_text("")
    config = json.loads((root / "langgraph.json").read_text())
    config["env"] = str(env_file)
    config["dependencies"] = [str(root)]
    config["graphs"] = {name: value.replace("./", str(root) + "/", 1) for name, value in config["graphs"].items()}
    if "http" in config:
        config["http"]["app"] = config["http"]["app"].replace("./", str(root) + "/", 1)
    config_file = tmp_path / "langgraph.json"
    config_file.write_text(json.dumps(config))
    log = tmp_path / "api.log"
    process = None
    try:
        with log.open("w") as output:
            process = subprocess.Popen(
                [str(Path(sys.executable).with_name("agentseek-api")), "dev", "--config", str(config_file), "--no-reload", "--no-browser", "--port", str(port)],
                cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT,
            )
            url = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                assert process.poll() is None, log.read_text()
                try:
                    if httpx.get(url + "/health", timeout=1, trust_env=False).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
            else:
                raise AssertionError(log.read_text())
            client = get_sync_client(url=url)
            assistant = client.assistants.search()[0]["assistant_id"]
            thread = client.threads.create()["thread_id"]
            events = list(client.runs.stream(thread, assistant, input={"messages": [{"role": "user", "content": "Plan and check evidence."}]},
                                             stream_mode=["values", "updates", "messages-tuple"]))
            assert not [e for e in events if e.event == "error"], events
            statuses = [e.data["todos"][0]["status"] for e in events if e.event == "values" and e.data.get("todos")]
            assert "in_progress" in statuses and statuses[-1] == "completed", events
            state = client.threads.get_state(thread)
            assert state["values"]["todos"][0]["status"] == "completed"
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        provider.shutdown()
        provider.server_close()
        worker.join(timeout=5)
