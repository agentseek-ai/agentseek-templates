.PHONY: check test lint format-check lock-check

check: lock-check lint format-check test

lock-check:
	uv lock --check

lint:
	uv run ruff check .

format-check:
	uv run ruff format --check .

test:
	uv run python -m pytest
