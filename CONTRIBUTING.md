# Contributing to Turbo Whisper

Thanks for helping make Turbo Whisper better. Pull requests from the community are very welcome, and this page explains what a PR needs so it can be reviewed and merged quickly.

## Before you start

- Open or find an issue first for anything beyond a small fix, so we can agree on the approach.
- One change per PR. Keep unrelated refactors, formatting sweeps and lockfile churn out of feature/fix PRs.
- Base your branch on the current `main` and keep it rebased if `main` moves.

## Development setup

```bash
git clone https://github.com/knowall-ai/turbo-whisper.git
cd turbo-whisper
uv sync --extra dev                 # dev = pytest, black, ruff
# Linux only: add the evdev typing backend as well
uv sync --extra dev --extra linux
# pip alternative: python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"  (add ",linux" on Linux)
uv run turbo-whisper # run the app
```

See `CLAUDE.md` for the module layout, how to kill stray instances, and the `sg input -c` wrapper needed for `/dev/uinput` typing on Linux.

## Coding standards

- Python 3.10+, formatted with `black src/` and linted with `ruff check src/`.
- Platform-specific code goes behind the existing backend pattern (see `hotkey.py` and `typer.py`): try the best backend for the platform, fall back gracefully, and never leave the user with *no* hotkey or *no* typing path.
- New config keys get a default in `config.py`, an entry in `config.example.json`, and a line in the JSON example under the README's **Configuration** section.
- Keep the docs in `docs/` current: `TROUBLESHOOTING.adoc` for user-facing fixes, `SOLUTION_DESIGN.adoc` when cross-platform behaviour changes.

## What every PR must include

1. **A clear description**: what changed, why, and which issue it fixes (`Fixes #NN`).
2. **Test evidence from a real run**: state which platform/session you tested on (e.g. *Ubuntu 24.04, KDE, X11*) and what you did. `py_compile` alone is not a test.
3. **Screenshots or a short recording** for anything a user can see or feel: the orb window, status text, typed output landing in an app, tray notifications. A before/after pair is ideal for bug fixes. Small screenshots committed under `docs/screenshots/` on your branch and referenced with a `raw.githubusercontent.com` URL render inline and travel with the PR.
4. **Backwards compatibility**: existing configs must keep loading and default behaviour must not change unless the PR says so.
5. **Cross-platform sanity**: if you can only test one platform, say so, and make sure other platforms are unaffected (guard with `platform.system()` / session checks).

## Review process

- Copilot and CodeRabbit review every PR automatically. Please address or reply to their comments; the maintainer reads them too.
- A maintainer will test the change locally and may push screenshots or small fixes to your branch (leave *Allow edits from maintainers* enabled).
- Once approved the PR is squash-merged. Version bumps and packaging (AUR, PPA) are handled by the maintainer.

## Reporting security issues

Please do not open public issues for vulnerabilities. See [SECURITY.md](SECURITY.md).
