# Capabilities Index

> **Boilerplate status:** The spec-writer sub-agent creates one file per capability in this directory. Each file describes exactly one discrete thing the agent can do.

---

## What Is a Capability?

A capability is a single, discrete action or behavior the agent performs. Examples:
- "Search the web for companies matching criteria X"
- "Draft a personalized email given a lead profile"
- "Send a Slack notification when a threshold is crossed"

## Capabilities in This Project

These are the **active** (v1) capabilities. Items deferred to later phases (inline charts, one-shot auto-report, Excel + deeper messy-data robustness, auto-findings/insights) are tracked in [`../roadmap.md`](../roadmap.md) `## Phases of Development` and appear as labelled NON-FUNCTIONAL stubs in the Phase-1 UI.

| Capability | File | Phase |
|-----------|------|-------|
| Dataset Upload | [dataset_upload.md](dataset_upload.md) | 1 (CSV); Excel in Phase 4 |
| Conversational Analysis (Answer + Show the Work) | [conversational_analysis.md](conversational_analysis.md) | 1 |
| Session History | [session_history.md](session_history.md) | 1 |

## How to Add a New Capability

Run `/zero-shot-build [description]` on the existing spec. The spec-writer sub-agent will:
1. Create a new file in this directory (`<name>.md`, no number prefix)
2. Update this index
3. Flag any dependencies on existing capabilities
4. Self-review that it fits the architecture and data model before returning

## Capability File Template

Each capability file should answer:
- **What it does** (one sentence)
- **Inputs** (what data it receives)
- **Outputs** (what it produces)
- **External calls** (APIs, LLMs, databases it touches)
- **Error cases** (what can go wrong and how it's handled)
- **Success criteria** (how we test it)
