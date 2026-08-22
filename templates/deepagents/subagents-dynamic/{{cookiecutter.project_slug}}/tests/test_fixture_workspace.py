from pathlib import Path

import pytest
from {{ cookiecutter.project_slug }}.fixture_workspace import FixtureWorkspace, make_fixture_tools


def _workspace(tmp_path: Path) -> FixtureWorkspace:
    root = tmp_path / "fixture"
    (root / "nested").mkdir(parents=True)
    (root / "zeta.py").write_text("VALUE = 2\n", encoding="utf-8")
    (root / "nested" / "alpha.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "notes.md").write_text("not code\n", encoding="utf-8")
    return FixtureWorkspace(root)


def test_glob_returns_stable_relative_python_paths(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)

    assert workspace.glob("**/*.py") == "nested/alpha.py\nzeta.py"


def test_glob_accepts_fixture_root_marker_without_exposing_absolute_paths(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)

    assert workspace.glob("/**/*.py") == "nested/alpha.py\nzeta.py"


def test_read_file_adds_line_numbers_for_evidence(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)

    assert workspace.read_file("nested/alpha.py") == "1: VALUE = 1"


def test_read_file_accepts_a_fixture_root_file_marker(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)

    assert workspace.read_file("/zeta.py") == "1: VALUE = 2"


@pytest.mark.parametrize(
    ("operation", "value"),
    [
        ("glob", "../*.py"),
        ("glob", "/tmp/*.py"),
        ("read_file", "../secret.py"),
        ("read_file", "/tmp/secret.py"),
        ("read_file", "notes.md"),
        ("read_file", "missing.py"),
    ],
)
def test_workspace_rejects_paths_outside_the_fixture_contract(
    tmp_path: Path,
    operation: str,
    value: str,
) -> None:
    workspace = _workspace(tmp_path)

    with pytest.raises(ValueError, match="fixture Python"):
        getattr(workspace, operation)(value)


def test_fixture_tools_exercise_the_read_only_workspace(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    glob_tool, read_tool = make_fixture_tools(workspace.root)

    assert glob_tool.invoke({"pattern": "**/*.py"}) == "nested/alpha.py\nzeta.py"
    assert read_tool.invoke({"path": "zeta.py"}) == "1: VALUE = 2"
