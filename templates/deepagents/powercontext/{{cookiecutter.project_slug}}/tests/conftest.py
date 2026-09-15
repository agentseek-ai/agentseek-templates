import pytest


@pytest.fixture
def anyio_backend():
    # The application uses asyncio queues, tasks, and operation deadlines.
    return "asyncio"
