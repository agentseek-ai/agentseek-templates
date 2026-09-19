import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "offline-test-key")
os.environ.setdefault("AGENTSEEK_MODEL_PROVIDER", "openai")
os.environ.setdefault("AGENTSEEK_MODEL", "offline-test-model")


@pytest.fixture
def anyio_backend():
    # The application uses asyncio queues, tasks, and operation deadlines.
    return "asyncio"
