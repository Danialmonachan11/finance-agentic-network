# Finance Agentic Network

A personal multi-agent finance-ops platform: LangGraph orchestration,
Postgres + Neo4j, real Gmail intake, a propose/execute approval split,
prompt-injection tests, and a FastAPI web app modeling a network of
companies (not a fixed single-operator setup).

**Read `docs/prd.md` first, then `BRAIN.md`, every session.** The PRD is the
rebuild target as of 2026-09-07; BRAIN.md is the history of what exists.

**BRAIN.md note:** It's the living source of truth —
current status per phase, every real decision made and why, and an honest
gap list for anything not built. This file only carries the agent-tooling
config those skills read from; project context lives there, not here.

## Agent skills

### Issue tracker

Local markdown under `.scratch/<feature>/` (create on first use). Remote: github.com/Danialmonachan11/finance-agentic-network. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-label vocabulary, unchanged (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/decisions/adr/` at the repo root (not written yet — `domain-modeling` owns that). See `docs/agents/domain.md`.
