install:
	@command -v uv >/dev/null 2>&1 || (echo "uv not found, installing..." && python -m pip install uv)
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run mypy .

setup: install

run:
	make lint
	uv run python -m websearch.main

# MCP stdio entry for the hub plugin's .mcp.json. stdout IS the JSON-RPC
# channel: the recipe must stay echo-silent (@) and write nothing to stdout
# before the server starts (no lint, no banners — those belong to `run`).
# Optional .env (gitignored, see .env.example): loaded only when present;
# already-exported environment variables take precedence (uv).
ENV_FILE := $(wildcard .env)
mcp:
	@uv run --no-dev $(if $(ENV_FILE),--env-file $(ENV_FILE),) python -m websearch.main

profile:
	make lint
	uv run python -m cProfile -s cumulative -m websearch.main
