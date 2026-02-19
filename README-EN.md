# MK2

A long-running, multi-session, self-protecting event-driven agent system.

## 1. Current Capabilities

1. Main pipeline: `Adapter -> Bus -> Router -> Worker -> Gate -> Agent -> emit -> Bus`
2. Gate: deterministic routing (`DROP / SINK / DELIVER`) with budget controls
3. System Reflex: runtime self-regulation based on nociception signals
4. Memory: integrated into Core (event/turn persistence, enabled by default, fail-open)
5. Testing: offline/integration layered strategy

## 2. Quick Start

```bash
# Install deps
uv sync

# Run offline baseline tests
uv run pytest -m "not integration" -q

# Start app
uv run python main.py
```

## 3. Test Commands

```bash
# Full suite (includes integration)
uv run pytest -q

# Offline only
uv run pytest -m "not integration" -q

# Integration only (real external deps)
uv run pytest -m integration -q
```

Notes:
1. LLM provider live tests in `integration` are gated by `RUN_LLM_LIVE_TESTS=1`.
2. Use `uv run pytest -q -rs` to see skip reasons.

## 4. Config Files

1. `config/gate.yaml`
2. `config/llm.yaml`
3. `config/memory.yaml`

Use environment variables for secrets; avoid committing plaintext keys.

## 5. Documentation Entry

1. `docs/README.md` (documentation index)
2. `docs/DEPLOYMENT.md` (deploy/run guide)
3. `docs/TESTING.md` (testing strategy)
4. `docs/MEMORY.md` (current memory implementation)
5. `docs/PROJECT_MODULE_DEEP_DIVE.md` (deep technical walkthrough)

## 6. Historical Docs

Legacy and phase-specific documents are archived under `docs/archive/`.
