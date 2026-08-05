from __future__ import annotations

import selectors
import subprocess
from pathlib import Path
from typing import Any

import pytest
from {{ cookiecutter.project_slug }} import runner
from {{ cookiecutter.project_slug }}.contracts import MAX_CANDIDATE_CHARS, candidate_id
from {{ cookiecutter.project_slug }}.runner import execute_candidate

PASSING_SOURCE = """\
def find_duplicates(values):
    seen = []
    duplicates = []
    for value in values:
        if value in seen:
            if value not in duplicates:
                duplicates.append(value)
        else:
            seen.append(value)
    return duplicates
"""

FAILING_SOURCE = """\
def find_duplicates(values):
    return []
"""


def test_passing_source_satisfies_every_fixed_case() -> None:
    result = execute_candidate(PASSING_SOURCE)

    assert result == {
        "candidate_id": candidate_id(PASSING_SOURCE),
        "ok": True,
        "behavior_failures": [],
        "profile_failures": [],
        "duration_ms": result["duration_ms"],
        "timed_out": False,
        "output_truncated": False,
    }
    assert result["duration_ms"] >= 0


def test_incomplete_candidate_names_each_failed_behavior_case() -> None:
    result = execute_candidate(FAILING_SOURCE)

    assert result["ok"] is False
    assert result["profile_failures"] == []
    assert {failure.split(":", maxsplit=1)[0] for failure in result["behavior_failures"]} == {
        "basic",
        "unhashable",
        "repeated_three_times",
    }


def test_basic_case_requires_first_duplicate_order() -> None:
    source = """\
def find_duplicates(values):
    return [1, 2] if values else []
"""

    result = execute_candidate(source)

    assert any(failure.startswith("basic:") for failure in result["behavior_failures"])


def test_input_mutation_is_a_behavior_failure_for_each_mutated_case() -> None:
    source = """\
def find_duplicates(values):
    original = list(values)
    values.append("changed")
    seen = []
    duplicates = []
    for value in original:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        else:
            seen.append(value)
    return duplicates
"""

    result = execute_candidate(source)

    mutation_failures = {
        failure.split(":", maxsplit=1)[0] for failure in result["behavior_failures"] if "input mutated" in failure
    }
    assert mutation_failures == {
        "basic",
        "empty",
        "no_duplicates",
        "unhashable",
        "repeated_three_times",
    }


@pytest.mark.parametrize(
    ("source", "failure"),
    [
        ("import os\n\ndef find_duplicates(values):\n    return []\n", "candidate_load"),
        ("def find_duplicates(values):\n    return [\n", "candidate_load"),
        ("def find_duplicates(values, extra):\n    return []\n", "candidate_signature"),
        (
            "handle = open('candidate-artifact', 'w')\n\ndef find_duplicates(values):\n    return []\n",
            "candidate_load",
        ),
    ],
)
def test_restricted_profile_rejects_imports_malformed_source_signature_and_builtins(
    source: str,
    failure: str,
) -> None:
    result = execute_candidate(source)

    assert result["ok"] is False
    assert result["behavior_failures"] == []
    assert result["profile_failures"] == [failure]
    assert source not in repr(result)


def test_infinite_candidate_times_out_and_is_reaped(monkeypatch: pytest.MonkeyPatch) -> None:
    processes: list[subprocess.Popen[bytes]] = []

    def process_factory(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        process = subprocess.Popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(runner, "_PROCESS_FACTORY", process_factory)

    result = execute_candidate("def find_duplicates(values):\n    while True:\n        pass\n")

    assert result["timed_out"] is True
    assert result["profile_failures"] == ["candidate_timeout"]
    assert processes and all(process.poll() is not None for process in processes)


def test_child_launch_has_fixed_restricted_profile_and_no_inherited_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launches: list[dict[str, Any]] = []
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-cross-boundary")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-cross-boundary")
    monkeypatch.setenv("GOOGLE_API_KEY", "must-not-cross-boundary")

    def process_factory(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        launches.append(kwargs.copy())
        return subprocess.Popen(*args, **kwargs)

    monkeypatch.setattr(runner, "_PROCESS_FACTORY", process_factory)

    result = execute_candidate(PASSING_SOURCE)

    assert result["ok"] is True
    assert len(launches) == 1
    launch = launches[0]
    assert launch["shell"] is False
    assert launch["env"] == {
        "PYTHONIOENCODING": "utf-8",
        "RUBRIC_CHILD_PROFILE": "restricted-v1",
    }
    assert launch["start_new_session"] is False


def test_anonymous_pipe_drain_does_not_require_selector_support(monkeypatch: pytest.MonkeyPatch) -> None:
    def unsupported_selector() -> selectors.BaseSelector:
        raise OSError("anonymous subprocess pipes are not selectable")

    monkeypatch.setattr(selectors, "DefaultSelector", unsupported_selector)

    result = execute_candidate(PASSING_SOURCE)

    assert result["ok"] is True


def test_overlong_source_is_rejected_before_process_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_process(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        raise AssertionError("overlong candidate must not create a process")

    monkeypatch.setattr(runner, "_PROCESS_FACTORY", unexpected_process)
    source = "#" * MAX_CANDIDATE_CHARS

    result = execute_candidate(source)

    assert result["profile_failures"] == ["candidate_too_long"]
    assert result["output_truncated"] is False


def test_oversized_candidate_result_is_safely_summarized_and_flagged() -> None:
    source = "def find_duplicates(values):\n    return ['x' * 70000]\n"

    result = execute_candidate(source)

    assert result["ok"] is False
    assert result["output_truncated"] is True
    assert len(repr(result)) < 4096


def test_large_integer_result_remains_a_concise_behavior_failure() -> None:
    source = "def find_duplicates(values):\n    return 10 ** 2000\n"

    result = execute_candidate(source)

    assert result["ok"] is False
    assert result["profile_failures"] == []
    assert result["behavior_failures"]
    assert result["output_truncated"] is True
    assert len(repr(result)) < 4096


def test_abnormal_child_output_is_terminated_at_the_capture_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    completion_marker = tmp_path / "child-finished"
    child = tmp_path / "oversized_child.py"
    child.write_text(
        "import pathlib, sys\n"
        "sys.stdin.buffer.read()\n"
        "sys.stdout.buffer.write(b'x' * (4 * 1024 * 1024))\n"
        "sys.stdout.buffer.flush()\n"
        f"pathlib.Path({str(completion_marker)!r}).write_text('finished')\n",
        encoding="utf-8",
    )
    processes: list[subprocess.Popen[bytes]] = []

    def process_factory(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        process = subprocess.Popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(runner, "_CHILD_PATH", child)
    monkeypatch.setattr(runner, "_PROCESS_FACTORY", process_factory)

    result = execute_candidate(PASSING_SOURCE)

    assert result["profile_failures"] == ["child_protocol"]
    assert result["output_truncated"] is True
    assert completion_marker.exists() is False
    assert processes and all(process.poll() is not None for process in processes)


def test_first_byte_over_capture_limit_terminates_before_child_continues(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    completion_marker = tmp_path / "cap-plus-one-child-finished"
    child = tmp_path / "cap_plus_one_child.py"
    child.write_text(
        "import pathlib, sys, time\n"
        "sys.stdin.buffer.read()\n"
        "sys.stdout.buffer.write(b'x' * ((64 * 1024) + 1))\n"
        "sys.stdout.buffer.flush()\n"
        "time.sleep(0.25)\n"
        f"pathlib.Path({str(completion_marker)!r}).write_text('finished')\n"
        "time.sleep(10)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "_CHILD_PATH", child)

    result = execute_candidate(PASSING_SOURCE)

    assert result["profile_failures"] == ["child_protocol"]
    assert result["output_truncated"] is True
    assert completion_marker.exists() is False


def test_combined_child_output_is_terminated_at_the_capture_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    completion_marker = tmp_path / "combined-child-finished"
    child = tmp_path / "combined_oversized_child.py"
    child.write_text(
        "import pathlib, sys, time\n"
        "sys.stdin.buffer.read()\n"
        "sys.stdout.buffer.write(b'x' * (40 * 1024))\n"
        "sys.stdout.buffer.flush()\n"
        "sys.stderr.buffer.write(b'x' * (40 * 1024))\n"
        "sys.stderr.buffer.flush()\n"
        "time.sleep(0.5)\n"
        f"pathlib.Path({str(completion_marker)!r}).write_text('finished')\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "_CHILD_PATH", child)

    result = execute_candidate(PASSING_SOURCE)

    assert result["profile_failures"] == ["child_protocol"]
    assert result["output_truncated"] is True
    assert completion_marker.exists() is False


def test_each_execution_uses_and_removes_a_distinct_temporary_cwd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_files_before = {path.relative_to(Path.cwd()) for path in Path.cwd().rglob("*")}
    working_directories: list[Path] = []

    def process_factory(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        working_directories.append(Path(kwargs["cwd"]))
        return subprocess.Popen(*args, **kwargs)

    monkeypatch.setattr(runner, "_PROCESS_FACTORY", process_factory)

    assert execute_candidate(PASSING_SOURCE)["ok"] is True
    assert execute_candidate(PASSING_SOURCE)["ok"] is True

    assert len(set(working_directories)) == 2
    assert all(not path.exists() for path in working_directories)
    assert {path.relative_to(Path.cwd()) for path in Path.cwd().rglob("*")} == project_files_before


def test_child_protocol_failures_never_expose_stderr_or_candidate_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    child = tmp_path / "broken_child.py"
    child.write_text(
        "import sys\nsys.stderr.write('secret-provider-representation')\nraise SystemExit(3)\n",
        encoding="utf-8",
    )
    source = "def find_duplicates(values):\n    return ['private-candidate-marker']\n"
    monkeypatch.setattr(runner, "_CHILD_PATH", child)

    result = execute_candidate(source)

    assert result["profile_failures"] == ["child_exit"]
    assert "secret-provider-representation" not in repr(result)
    assert "private-candidate-marker" not in repr(result)


def test_cancellation_terminates_and_reaps_only_the_owned_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processes: list[subprocess.Popen[bytes]] = []

    def process_factory(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        process = subprocess.Popen(*args, **kwargs)
        processes.append(process)
        return process

    def interrupt(*args: Any, **kwargs: Any) -> tuple[bytes, bytes, bool]:
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "_PROCESS_FACTORY", process_factory)
    monkeypatch.setattr(runner, "_drain_process", interrupt, raising=False)

    with pytest.raises(KeyboardInterrupt):
        execute_candidate(PASSING_SOURCE)

    assert processes and all(process.poll() is not None for process in processes)
