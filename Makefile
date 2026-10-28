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

profile:
	make lint
	uv run python -m cProfile -s cumulative -m websearch.main

# Parity judge. judge: the real comparison, old spec vs port (FIX-FORWARD
# spec). judge-old / judge-fixed: determinism self-checks of each binary
# against its own contract (amended scenarios are side-branched).
# NEW is a SINGLE executable path (the harness spawns [path] with no args) —
# for the port, ship a wrapper script that execs the server.
JUDGE_OLD := migration/judge/bin/websearch-go
JUDGE_FIXED := migration/judge/bin/websearch-fixedgo

judge:
	@test -n "$(NEW)" || { echo "NEW is unset — usage: make judge NEW=<single executable path of the port>"; exit 2; }
	uv run python migration/judge/run.py --old $(JUDGE_OLD) --new $(NEW)

judge-old:
	uv run python migration/judge/run.py --old $(JUDGE_OLD) --sides old,old

judge-fixed:
	uv run python migration/judge/run.py --old $(JUDGE_FIXED) --sides new,new
