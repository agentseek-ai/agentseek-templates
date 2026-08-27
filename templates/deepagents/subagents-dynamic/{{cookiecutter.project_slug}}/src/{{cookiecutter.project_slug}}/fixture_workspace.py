"""Narrow, read-only access to bundled Python teaching fixtures."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from langchain_core.tools import BaseTool, tool


class FixtureWorkspace:
    """Expose only Python files below one resolved fixture directory."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        if not self.root.is_dir():
            raise ValueError(f"Expected a fixture directory, got {root}")

    @staticmethod
    def _validate_relative(value: str) -> PurePosixPath:
        requested = PurePosixPath(value)
        if requested.is_absolute() or not requested.parts or ".." in requested.parts:
            raise ValueError(f"Expected a relative fixture Python path or pattern, got {value!r}")
        return requested

    def glob(self, pattern: str) -> str:
        """Return matching Python paths relative to the fixture root in stable order."""
        normalized_pattern = pattern[1:] if pattern.startswith("/**/") else pattern
        requested = self._validate_relative(normalized_pattern)
        if requested.suffix not in {"", ".py"}:
            raise ValueError(f"Expected a fixture Python glob, got {pattern!r}")
        matches = sorted(
            path.relative_to(self.root).as_posix()
            for path in self.root.glob(requested.as_posix())
            if path.is_file() and path.suffix == ".py" and path.resolve().is_relative_to(self.root)
        )
        return "\n".join(matches)

    def read_file(self, relative_path: str) -> str:
        """Read one Python fixture with stable one-based line numbers."""
        normalized_path = (
            relative_path[1:]
            if relative_path.startswith("/") and "/" not in relative_path[1:]
            else relative_path
        )
        requested = self._validate_relative(normalized_path)
        candidate = (self.root / requested.as_posix()).resolve()
        if (
            requested.suffix != ".py"
            or not candidate.is_relative_to(self.root)
            or not candidate.is_file()
        ):
            raise ValueError(f"Expected an existing fixture Python file, got {relative_path!r}")
        lines = candidate.read_text(encoding="utf-8").splitlines()
        return "\n".join(f"{line_number}: {line}" for line_number, line in enumerate(lines, start=1))


def make_fixture_tools(root: Path) -> tuple[BaseTool, BaseTool]:
    """Bind official-style glob/read tools to one teaching fixture."""
    workspace = FixtureWorkspace(root)

    @tool("glob")
    def glob_tool(pattern: str) -> str:
        """List bundled Python files with **/*.py (or fixture-root marker /**/*.py)."""
        return workspace.glob(pattern)

    @tool("read_file")
    def read_file_tool(path: str) -> str:
        """Read one bundled Python file by relative path (or /file.py root marker)."""
        return workspace.read_file(path)

    return glob_tool, read_file_tool
