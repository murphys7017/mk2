# 🧠 Project Overview – A Long-Running Agent System

## What This Project Is

This project is **not just a conversational AI wrapper**.

It is a **long-running, multi-session, self-regulating agent system** designed with biological metaphors:

> Perception → Reflex → Cognition → Action → Feedback → Self-Regulation

The goal is to build an agent that can:

* Run continuously
* Handle multiple sessions concurrently
* Protect itself under overload
* Degrade gracefully
* Recover automatically
* Support tool and model hierarchy
* Remain observable and controllable at runtime

---

# 🏗 System Architecture Overview

The system is organized into **three structural layers**, inspired by biological systems.

---

## 1️⃣ Brainstem Layer (Gate) — Reflex & Protection

This layer is fully implemented.

### Responsibilities

* Scene classification
* Scoring & routing
* Deduplication
* Rate control
* Overload protection
* Drop / Sink / Deliver decision
* Runtime overrides (emergency mode, forced low model)

### Key Properties

* Deterministic
* Rule-based
* Fast
* Config-driven (YAML)
* Hot-reloadable
* No LLM involved

The Gate acts as a **reflex system**, not a reasoning engine.

---

## 2️⃣ Cognitive Layer (Agent) — Intelligence & Planning

This layer is entering active development.

### Planned Responsibilities

* Intent judgment
* Planning
* Memory management
* Tool decision
* Multi-model strategy
* Structured response generation

The Agent only receives inputs that pass the Gate.

It does not decide whether to respond — only *how* to respond.

---

## 3️⃣ Autonomic Layer (System Reflex)

This layer enables self-regulation.

### Closed Loop Implemented

```
Gate emits ALERT
→ System session aggregates signals
→ Reflex controller evaluates health
→ Overrides updated
→ Gate behavior changes
→ CONTROL event broadcast
```

### Current Capabilities

* Emergency mode activation
* Forced low-model mode
* Drop burst detection
* TTL-based temporary tuning
* Agent tuning suggestions (whitelisted, safe, time-bound)
* Automatic recovery

### Design Principles

* No LLM involvement
* No heavy reasoning
* Pure rule-based reflex
* Observable transitions
* Safe override boundaries

---

# 🔄 Runtime Flow

```
Adapter
→ Observation
→ InputBus
→ SessionRouter
→ SessionWorker
→ Gate (Brainstem)
→ Agent (Cognition)
→ Tool (future)
→ Observation feedback
→ System Reflex (Autonomic)
```

All state transitions occur via structured Observations.

There are no hidden side channels.

---

# 🔧 Configuration System

The Gate is configured via YAML:

* Scene policies
* Scoring weights
* Dedup windows
* Drop escalation rules
* Runtime overrides

Configuration supports:

* Default fallback
* Strong typing
* Hot reload with snapshot replacement
* Runtime modification via system reflex

---

# 🛡 Runtime Safety Model

The system enforces strict boundaries:

* Gate never calls Agent
* Agent cannot directly modify Gate
* Agent may only suggest tuning
* System reflex is the sole authority for override execution
* All changes emit observable events

This prevents unstable feedback loops.

---

# 📈 Current Completion Stage

Completed:

* Input pipeline
* Multi-session routing
* Gate reflex system
* YAML configuration + hot reload
* Runtime overrides
* System reflex controller
* Agent notification mechanism
* Agent tuning suggestion mechanism

Stable closed loop exists from input to self-regulation.

---

# 🚀 Next Phase: Cognitive Expansion

Focus shifts toward:

* Agent planning architecture
* Memory refinement
* Tool registry and execution layer
* Tool result reintegration through Gate

The structural foundation is complete.

---

# 🎯 Final Vision

This project aims to evolve into:

> A self-protecting, long-running agent system
> that can reason, act, adapt, and survive under dynamic conditions.

Not just intelligent.
Not just reactive.
But structurally resilient.



---

# 📚 Documentation

- [docs/README.md](docs/README.md) - Documentation index
- [docs/PROJECT_MODULE_DEEP_DIVE.md](docs/PROJECT_MODULE_DEEP_DIVE.md) - Deep technical walkthrough aligned to current code
