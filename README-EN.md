# MK2

A long-running, multi-session, event-driven agent system with built-in protection and self-regulation.

## Project Philosophy

MK2 is not a thin chat wrapper around an LLM. It is designed as a structural system where stability comes first:

1. Long-running reliability over short-term demo behavior
2. Explicit boundaries over implicit coupling
3. Observability, degradation, and recovery over “looks smart”

The architecture follows a life-like layered model:

1. Perception (Adapter / Observation)
2. Reflex (Gate)
3. Cognition (Agent)
4. Autonomic regulation (System Reflex)
5. Memory (Persistence + knowledge/config)

## Architecture Overview

### 1. Brainstem Layer: Gate (Reflex and Protection)

Responsibilities:

1. Scene inference
2. Scoring and budget mapping
3. DROP / SINK / DELIVER decision
4. Overload protection and runtime overrides

Properties:

1. Rule-based
2. No LLM in the decision core
3. Fast and predictable
4. YAML-driven and hot-reloadable

### 2. Cognitive Layer: Agent (Planning and Answering)

Responsibilities:

1. Planner builds information needs
2. EvidenceRunner gathers evidence
3. Answerer generates response
4. Speaker/PostProcessor renders outputs

Boundary:

1. Agent handles only Gate-delivered requests
2. Agent does not directly modify Gate policy

### 3. Autonomic Layer: System Reflex (Self-regulation)

Responsibilities:

1. Aggregate pain/anomaly signals (Nociception)
2. Trigger temporary tuning (for example emergency mode)
3. Broadcast system state changes via CONTROL observations

### 4. Memory Layer: Persistence and Knowledge

Integrated into Core runtime flow:

1. Event persistence (Observation level)
2. Turn persistence (Agent call level)
3. Markdown Vault for config/knowledge docs
4. Failure queue with retry/spill/rotation/dead-letter

Design rule: `fail-open` — memory failures must not block the main response path.

## Runtime Flow

```text
Adapter
-> Observation
-> InputBus
-> SessionRouter
-> SessionWorker
-> Gate
-> Agent
-> emit Observation
-> back to Bus
-> System Reflex / Memory persistence
```

## Safety and Boundaries

Hard constraints:

1. Gate does not call Agent
2. Agent does not directly mutate Gate config
3. Runtime tuning is applied through System Reflex
4. State changes propagate via observations, not hidden side channels

## Current Status

Current mainline already has:

1. Multi-session isolation and concurrency
2. Gate policy pipeline with hot reload
3. Agent MVP orchestration
4. System Reflex feedback loop
5. Memory persistence in Core runtime
6. Layered testing strategy (`offline` / `integration`)

## Quick Start

```bash
# Install dependencies
uv sync

# Offline baseline tests (recommended)
uv run pytest -m "not integration" -q

# Start
uv run python main.py
```

## Test Commands

```bash
# Full suite (includes integration)
uv run pytest -q

# Offline only
uv run pytest -m "not integration" -q

# Integration only (real external dependencies)
uv run pytest -m integration -q
```

Notes:

1. LLM provider live tests are gated by `RUN_LLM_LIVE_TESTS=1` (see `tests/test_llm_providers.py`)
2. Use `uv run pytest -q -rs` to inspect skip reasons

## Key Config Files

1. `config/gate.yaml`
2. `config/llm.yaml`
3. `config/memory.yaml`

Use environment variables for secrets. Avoid committing plaintext keys.

## Documentation Entry Points

1. `docs/README.md` (documentation index)
2. `docs/DEPLOYMENT.md` (deployment and runtime guide)
3. `docs/TESTING.md` (testing strategy)
4. `docs/MEMORY.md` (current memory implementation)
5. `docs/PROJECT_MODULE_DEEP_DIVE.md` (deep technical walkthrough)
6. `docs/DESIGN_DECISIONS.md` (key architecture decisions)

## Historical Documents

Historical/phase-specific docs are archived under `docs/archive/` and are not the source of truth for current behavior.
