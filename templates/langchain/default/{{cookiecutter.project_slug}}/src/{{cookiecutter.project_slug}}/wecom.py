"""WeCom gateway launcher for the LangChain template."""

from __future__ import annotations

from .dev import _build_env, _project_root, _spawn, _terminate


def main() -> None:
    """Run the upstream WeCom AI-bot channel through the shared agent spec."""
    root = _project_root()
    gateway = _spawn(
        ["bub", "gateway", "--enable-channel", "wecom"], cwd=root, env=_build_env(root)
    )
    try:
        try:
            raise SystemExit(gateway.wait())
        except KeyboardInterrupt:
            raise SystemExit(0) from None
    finally:
        _terminate(gateway)
