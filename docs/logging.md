# Logging Guide

## Goal

Use a single logging system (`loguru`) with clear level semantics:

- `INFO`: lifecycle and user-facing milestones.
- `DEBUG`: high-frequency pipeline details.
- `WARNING`: recoverable problems or degraded behavior.
- `ERROR` / `EXCEPTION`: failures requiring investigation.

## Global Setup

Project-wide setup lives in `src/logging_config.py`.

- Default initialization happens in `src/__init__.py`.
- Any standard-library `logging` records are intercepted and forwarded to `loguru`.
- Reconfiguration is supported via `setup_logging(..., force=True)`.

## Current Policy

### Core (`src/core.py`)

- Startup/shutdown/session-GC: `INFO`.
- Per-observation flow details:
  - `[WORKER:IN]`
  - `[GATE:CTX]`
  - `[GATE:OUT]`
  - `[DELIVER]`
  are `DEBUG`.
- Frequent per-message summaries are `DEBUG`.
- Overload/cooldown/fanout failures remain `WARNING`.
- Unhandled exceptions use `logger.exception(...)`.

### CLI Adapter (`src/adapters/cli_adapter.py`)

- User command acknowledgements: `INFO`.
- Internal adapter/bus payload dumps: `DEBUG`.
- Invalid command parameters: `WARNING`.
- Runtime exceptions: `EXCEPTION`.

### Agent Orchestrator (`src/agent/orchestrator.py`)

- Step-level progress and completion: `DEBUG`.
- Step failures: `ERROR`.
- Unexpected top-level failures: `EXCEPTION`.

## Demo Trace Mode

`tools/demo_e2e.py` uses `setup_logging(..., trace_only=True)` and custom trace tags.
This mode keeps:

- explicit trace logs, and
- `WARNING`/`ERROR`/`CRITICAL`

while hiding unrelated `INFO` noise.

## Recommended Usage

- Daily development:
  - `setup_logging(level="INFO")`
- Pipeline debugging:
  - `setup_logging(level="DEBUG", force=True)`
- E2E tracing:
  - run `tools/demo_e2e.py` (already configured for trace-focused output)
