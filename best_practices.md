# \ud83d\udcd8 Project Best Practices

## 1. Project Purpose
This repository implements an automation bot for TTUEX "copy trading". It provides:
- A CLI to log in and copy-trade orders across multiple accounts
- A FastAPI webhook server (for integrations)
- A Telegram bot for notifications and background triggers
- A Playwright-based browser automation workflow with robust retries, storage-state reuse, and diagnostics

Primary domains: web automation (Playwright), orchestration across accounts, operational reliability (retries, logs, diagnostics), and chat/HTTP integrations.

## 2. Project Structure
- `src/ttuex_bot/`
  - `cli.py`: CLI entrypoint (Click) with commands: `login`, `copy-trade`, `serve`, `run-telegram`.
  - `config.py`: Pydantic settings (env-file-based) for URLs, selectors, timeouts, concurrency, logging, Telegram/Twilio.
  - `actions.py`: Interface-agnostic actions (per-account functions) used by CLI and bots; wires the `TtuexWorkflow` with Playwright.
  - `orchestrator.py`: Concurrency orchestration across accounts (1 context per account, semaphore-limited).
  - `playwright_adapter.py`: Thin DI-friendly wrapper around Playwright (launch args, context setup, resource blocking, timeouts).
  - `core/workflow.py`: Main TtuexWorkflow (login → navigate → enter order → execute follow-up); rich error classification, retries, and diagnostics.
  - `core/workflow_radical_fast.py`: Alternative experimental workflow with ultra-aggressive timeouts and immediate modal/toast parsing.
  - `server/main.py`: FastAPI app (webhook endpoints for integrations).
  - `telegram_bot.py`: Telegram bot integration (Telethon), background job runner.
  - `utils/`: logging (structlog), retry logic, error classification, web utilities (popup/overlay handlers), translators.
- `tests/`: pytest, pytest-asyncio; tests for CLI and error handling.
- Root files: `.env`, `accounts.json`, `Dockerfile`, `pyproject.toml`, `requirements.txt`.

Separation of concerns:
- Orchestration (orchestrator) vs. per-account actions (actions) vs. workflow steps (core/workflow)
- Config/Selectors centralized in `config.py`
- Web automation behaviors in `playwright_adapter.py` and `utils/web_utils.py`
- Interfaces (CLI/Server/Telegram) decoupled from actions/workflows

Entry points:
- `python -m ttuex_bot` → CLI
- `python -m ttuex_bot run-telegram` → Telegram bot
- `python -m ttuex_bot serve` → FastAPI server

## 3. Test Strategy
- Framework: Pytest + pytest-asyncio
- Organization: functional tests for CLI and error handling under `tests/`
- Guidelines:
  - Prefer unit tests for utils (retry, classifiers, web_utils) using mocks.
  - Use PlaywrightAdapter DI to mock browser/context/page in tests (no real browser in unit tests).
  - Add integration tests in a controlled environment for the workflow with a fake/mocked page state.
  - For regressions, capture report dicts from workflows and assert on steps/success/errors.
  - Avoid flakiness by controlling timeouts and using deterministic simulated steps (dry_run) for logic tests.

## 4. Code Style
- Python 3.11+, Pydantic v2-based config
- Typing: use precise types (Optional, Dict[str, Any], SecretStr for passwords); expose clear function signatures
- Async: leverage `asyncio` end-to-end; `async_retry` decorator for transient errors with exponential backoff
- Logging: structlog with JSON/console mode; bind `account_name` or contextual fields; avoid noisy prints (configure level via `.env`)
- Errors: classify with `TemporaryError` vs `PermanentError`; use `ErrorClassifier` and `classify_and_raise`
- Diagnostics: on failure save screenshots/HTML artifacts and include essential context in logs
- Config-over-code: tune timeouts and selectors via `AppConfig` to minimize code changes

## 5. Common Patterns
- DI-friendly abstraction: `PlaywrightAdapter` to enable mocking and context setup
- Orchestration pattern: semaphore-limited concurrent tasks per account, isolated `BrowserContext`
- Workflow as a sequence of retriable steps with per-step diagnostics
- Web resilience patterns: popup/overlay handling (`WebErrorHandler`), safe wait/click helpers, retryable timeouts
- Storage-state per account: `storage_states/<account>.json` to skip relogins

## 6. Do's and Don'ts
### ✅ Do
- Centralize selectors/timeouts in `config.py`
- Always call `WebErrorHandler.handle_common_popups()` before critical interactions
- Use `async_retry` on network/DOM-sensitive steps
- Log with contextual fields (account, step, URL) and keep logs at INFO/WARNING in production
- Save debugging artifacts on failures (screenshots/HTML)
- Keep `MAX_CONCURRENT_ACCOUNTS` small; 1 for low resource environments
- Use `--performant` to block heavy resources; ensure critical resources are not blocked

### ❌ Don't
- Hardcode timeouts/selectors inside steps when they should be in config
- Overly rely on deep CSS paths for critical fields (use robust/fallback selectors instead)
- Swallow exceptions silently; always classify and either retry or return a clear failure
- Mix UI language assumptions (FR-only selectors) without multi-language fallbacks
- Run without validating which workflow module is loaded (avoid stale installed versions)

## 7. Tools & Dependencies
- Playwright: browser automation
- FastAPI + Uvicorn: webhook server
- Click: CLI
- Telethon: Telegram bot
- Pydantic + pydantic-settings: configuration and secrets
- Structlog: logging
- Pytest + pytest-asyncio: tests

Setup:
```bash
pip install -r requirements.txt
python -m playwright install
# Optional: pip install -e .  # to run from source and avoid stale installs
```

## 8. Other Notes
- Multiple workflows exist; ensure the intended one is used (`core/workflow.py`). Restart long-running processes (Telegram bot) after code changes.
- Selectors may differ by language; prefer multi-language selectors for key actions (e.g., follow button).
- For reliability, add fallback selectors for the order number input and re-check overlays immediately before clicking the follow button.
- When measuring performance, disable runtime padding via `.env` and time the entire CLI invocation using OS tools (PowerShell `Measure-Command` or a Python wrapper).
