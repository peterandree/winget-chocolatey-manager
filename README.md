# wincoman — Windows Computer Manager

Find Windows apps not managed by WinGet, Chocolatey, or Scoop — and register
them with Chocolatey in one command.

## What it does

1. **Scans** the Windows registry for all installed programs
2. **Checks** WinGet, Chocolatey, and Scoop to find which apps are already managed
3. **Searches** the Chocolatey repository for matching packages for the unmanaged remainder
4. **Registers** found packages — interactively, automatically, or exports a batch file

## Requirements

| Requirement | Notes |
|---|---|
| Windows 10 / 11 | Required |
| Python 3.11+ | Via [uv](https://docs.astral.sh/uv/) — no manual install needed |
| [uv](https://docs.astral.sh/uv/) | Fast Python project manager |
| WinGet | Pre-installed on Windows 11; [download for Windows 10](https://aka.ms/getwinget) |
| Chocolatey | [Installation guide](https://chocolatey.org/install) |
| Administrator privileges | Required for `choco install` |
| Scoop | Optional — detected automatically if installed |

## Quickstart

```powershell
# 1. Install uv (if not already installed)
winget install astral-sh.uv

# 2. Clone
git clone https://github.com/peterandree/winget-chocolatey-manager.git
cd winget-chocolatey-manager

# 3. Run (as Administrator)
uv run wincoman
```

> **Always run as Administrator.** `choco install` requires elevation.

## CLI Reference

```
uv run wincoman [OPTIONS]
```

| Flag | Description |
|---|---|
| _(none)_ | Full interactive scan |
| `--dry-run` | Preview all actions — no packages are installed |
| `--auto` | Register all matches without prompting |
| `--export-only` | Write a `.bat` file instead of installing |
| `--output PATH` | Batch file destination (used with `--export-only`) |
| `--exclude-microsoft` | Filter out Microsoft/Windows-published apps from scan |
| `--min-score INT` | Fuzzy-match threshold 0–100 (default: 60) |
| `--use-cache` | Skip scan and reuse results from a previous run |
| `--cache-file PATH` | JSON cache file path (default: `~/.wincoman/state.json`) |
| `--log-file PATH` | Tee log output to a file |
| `--quiet` / `-q` | Suppress INFO output (warnings and errors only) |

### Common examples

```powershell
# Preview what would be registered — no changes made
uv run wincoman --dry-run

# Register everything automatically (CI / headless)
uv run wincoman --auto

# Export a batch file for manual review
uv run wincoman --export-only --output register.bat

# Re-run from last scan's cache (fast)
uv run wincoman --use-cache

# Strict matching — only high-confidence package matches
uv run wincoman --min-score 80

# Log everything to a file
uv run wincoman --log-file wincoman.log
```

## Interactive workflow

When run without flags, wincoman guides you through five steps:

```
wincoman — Windows Computer Manager
======================================================================

Step 1/5: Checking WinGet Managed Packages
Found 47 apps managed by WinGet

Step 2/5: Scanning Installed Programs
Found 124 installed programs

Step 3/5: Checking Chocolatey Packages
Found 12 packages in Chocolatey

Step 4/5: Finding Unmanaged Apps
Found 23 unmanaged apps

Step 5/5: Searching Chocolatey Repository
Progress: 23/23 apps processed...

======================================================================
  RESULTS
======================================================================

Found 8 apps that can be registered with Chocolatey:

----------------------------------------------------------------------
Installed App                            Chocolatey Package
----------------------------------------------------------------------
7-Zip 23.01                              7zip
VLC media player                         vlc
Notepad++ (64-bit)                       notepadplusplus
----------------------------------------------------------------------

Registration options:
  1. Register all packages automatically
  2. Review and select packages individually
  3. Export to batch file (manual registration)
  4. Exit without registering
```

## Architecture

wincoman is a modular Python package under `src/wincoman/`:

```
src/wincoman/
├── cli.py           CLI entry point (_build_arg_parser, main)
├── runner.py        Orchestrator — wires all pipeline stages
├── config.py        ScanConfig dataclass (single source of configuration)
├── shell.py         Subprocess wrapper (run_command, timeout handling)
├── scoring.py       fuzzy_score, normalize_name, versions_differ
├── registry.py      Windows registry scan via PowerShell
├── detector.py      find_unmanaged — cross-references installed vs managers
├── cache.py         JSON scan-result persistence (save/load)
├── reporter.py      display_results, export_to_batch
├── installer.py     register_packages, register_interactive
└── matchers/
    ├── base.py      BasePackageManager ABC, SearchablePackageManager, PackageMatch
    ├── winget.py    WinGetManager adapter
    ├── chocolatey.py ChocolateyManager adapter (list + search)
    └── scoop.py     ScoopManager adapter (optional, graceful skip)
```

Adding support for a new package manager (e.g. pip, npm) requires only a
new adapter file in `matchers/` — no changes to `detector.py` or `runner.py`.

## Development

```powershell
# Install all dependencies (including dev)
uv sync

# Run tests
uv run pytest tests/

# Run tests with coverage
uv run coverage run -m pytest tests/
uv run coverage report

# Run a specific test file
uv run pytest tests/test_matchers_chocolatey.py -v
```

### Project structure

```
winget-chocolatey-manager/
├── pyproject.toml           Project metadata and dependencies
├── uv.lock                  Locked dependency versions
├── register_unmanaged_apps.py  Deprecated shim (removed in v2.0)
├── src/wincoman/            Main package (see Architecture above)
└── tests/                   170 tests, 90% coverage
    ├── conftest.py
    ├── test_cli.py
    ├── test_config.py
    ├── test_shell.py
    ├── test_scoring.py
    ├── test_registry.py
    ├── test_cache.py
    ├── test_detector.py
    ├── test_reporter.py
    ├── test_installer.py
    ├── test_runner.py
    ├── test_matchers_base.py
    ├── test_matchers_winget.py
    ├── test_matchers_scoop.py
    └── test_matchers_chocolatey.py
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Add or update tests for your change
4. Run `uv run pytest tests/` — all tests must pass
5. Commit (`git commit -m 'feat: my feature'`) and push
6. Open a Pull Request

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `WinGet is not available` | winget not on PATH | Windows 11: update Windows; Windows 10: [download winget](https://aka.ms/getwinget) |
| `Chocolatey is not available` | choco not installed | [Install Chocolatey](https://chocolatey.org/install) |
| `Not running as Administrator` | No elevation | Re-run PowerShell as Administrator |
| Step 5 is slow | Chocolatey API queries per app | Normal — ~2–5 min for 20+ apps; use `--use-cache` on re-runs |
| App not detected | No registry entry | Portable/standalone apps don't appear in the registry scan |
| Low-confidence match | Fuzzy threshold too low | Raise `--min-score` (e.g. `--min-score 80`) |

## FAQ

**Do I need both WinGet and Chocolatey?**
WinGet is your primary manager. Install Chocolatey only for apps WinGet doesn't cover.

**Will this reinstall my applications?**
No. `choco install --force` only registers the app in Chocolatey's database; it does not reinstall the software.

**What if I already have some apps in Chocolatey?**
They are automatically detected and skipped.

**Can I run this without Scoop installed?**
Yes. The Scoop check is optional and skipped gracefully if Scoop is not on PATH.

**Is `register_unmanaged_apps.py` still supported?**
It remains as a deprecated shim and will be removed in v2.0. Use `uv run wincoman` instead.

## Version history

- **1.3.0** — Modular refactor: `src/wincoman/` package, `wincoman` CLI, uv project setup,
  adapter plugin system (WinGet/Chocolatey/Scoop), 170 tests, 90% coverage
- **1.2.0** — Scoop support, JSON cache (`--use-cache`), version mismatch detection,
  argparse CLI, dry-run mode, structured logging
- **1.1.0** — Comprehensive error handling, direct interactive registration,
  admin privilege detection, progress tracking
- **1.0.0** — Initial release: WinGet integration, Chocolatey automation, batch export

## License

MIT — see [LICENSE](LICENSE).

## Support

- [Open an issue](https://github.com/peterandree/winget-chocolatey-manager/issues) with your Windows version, Python version, WinGet version, and Chocolatey version
- Check the [Security Policy](SECURITY.md) for reporting vulnerabilities

