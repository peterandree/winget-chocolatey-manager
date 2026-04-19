# winget-chocolatey-manager (wincoman)

Windows CLI tool that finds installed apps unmanaged by WinGet or Chocolatey and registers them with Chocolatey when no WinGet match exists. Runs on Windows, requires admin rights. Published as PyPI package `wincoman`.

## Tech Stack

- Python >= 3.11
- `rapidfuzz` >= 3.0 — fuzzy name matching between installed apps and package manager results
- Build: `hatchling` via `pyproject.toml`
- Package manager: `uv` (lockfile: `uv.lock`)
- Testing: `pytest` >= 8.2, `pytest-mock` >= 3.14, `coverage[toml]` >= 7.5
- Entry point: `wincoman` CLI → `src/wincoman/cli:main`

## Project Structure

```
src/wincoman/
  cli.py           — argparse entry point, orchestrates the run
  runner.py        — main orchestration logic: scan → match → report → install
  detector.py      — detects installed apps (WinGet/Choco/registry)
  installer.py     — executes Chocolatey registration/install commands
  registry.py      — reads Windows registry for installed apps
  matcher.py       — fuzzy matching logic using rapidfuzz
  matchers/        — per-source matcher implementations
  scoring.py       — match confidence scoring
  reporter.py      — console output, tables, summaries
  cache.py         — caches WinGet/Choco query results to avoid slow repeated calls
  config.py        — configuration loading and defaults
  __init__.py      — version export
  __main__.py      — enables `python -m wincoman`
tests/             — pytest test suite (mirrors src/wincoman/ structure)
register_unmanaged_apps.py  — legacy standalone script (do not extend; kept for compatibility)
```

## Commands

```bash
# Install dev dependencies
uv sync

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov

# Run the tool locally
uv run wincoman

# Lint (no linter configured — use common sense; no wildcard imports, type hints on public functions)
```

## Coding Conventions

- Type hints on all public functions and method signatures
- snake_case functions and variables, PascalCase classes
- No wildcard imports
- All subprocess/shell calls go through `shell.py` — never call `subprocess` directly elsewhere
- All WinGet/Choco CLI invocations must go through `shell.py` helpers, not inline `subprocess.run`
- Cache expensive shell calls via `cache.py` — never call WinGet/Choco more than once per session
- Tests must mock all shell calls — no real WinGet/Choco calls in tests

✅ Good — shell call via abstraction:
```python
from wincoman.shell import run_winget_list
results = run_winget_list()
```

❌ Bad — inline subprocess:
```python
import subprocess
result = subprocess.run(["winget", "list"], capture_output=True)
```

## Agent Boundaries

- ✅ Always: write to `src/wincoman/`, add tests in `tests/`, run `uv run pytest` before marking done
- ✅ Always: read existing file before editing — check `shell.py` and `cache.py` before adding any new subprocess or caching logic
- ⚠️ Ask first: adding a new dependency to `pyproject.toml`, changing the CLI interface or argument names
- 🚫 Never: call `subprocess` directly outside `shell.py`, extend `register_unmanaged_apps.py`, commit secrets or user-specific paths
