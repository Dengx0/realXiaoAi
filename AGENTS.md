# Repository Guidelines

## Project Structure & Module Organization
Core application code lives in `xiaoi/`. Keep HTTP handlers in `xiaoi/http_api.py`, device-control logic in `xiaoi/client.py`, config loading in `xiaoi/config.py`, and service assembly in `xiaoi/service.py`. Audio generation code is under `aiaudio/`. The CLI entrypoint is `main.py`. Sample payloads live in `fixtures/`. Generated MP3 files belong in `generated_audio/` and should not be edited by hand.

## Build, Test, and Development Commands
This repo does not include `pyproject.toml` or a lockfile, so use a lightweight local environment.

```powershell
uv pip install requests
copy config.example.json config.json
python main.py --config config.json
```

`uv pip install requests` installs the dependency documented in `README.md`. `python main.py --config config.json` starts message polling, the control HTTP API, and the audio generation API. For manual checks, use `python main.py --help` and exercise the HTTP endpoints directly.

## Coding Style & Naming Conventions
Use Python with 4-space indentation, type hints where practical, and small, readable functions. Follow the existing module split instead of adding large mixed-purpose files. Prefer `snake_case` for functions, variables, and modules, `PascalCase` for classes, and explicit names such as `run_control_http_server`. Keep comments brief and only where behavior is not obvious.

## Testing Guidelines
There is currently no maintained automated test suite in this working copy. Validate changes with focused manual HTTP requests against a real device and keep example payloads in `fixtures/` when adding new protocol coverage.

## Commit & Pull Request Guidelines
Git history is not available in this working copy, so no repository-specific commit convention can be inferred. Use short, imperative commit subjects such as `add xiaoai volume endpoint`. Keep each commit focused on one change. Pull requests should include a summary, affected paths, config changes, manual verification notes, and example request/response payloads for API changes.

## Security & Configuration Tips
Do not commit real `config.json`, tokens, device IDs, or generated credentials. Treat `config.example.json` as the only safe template. When changing auth or public HTTP settings, update `README.md` and verify token-protected endpoints still behave correctly.
