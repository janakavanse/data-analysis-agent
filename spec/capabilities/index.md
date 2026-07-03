# Capabilities Index

---

## What Is a Capability?

A capability is a single, discrete action or behavior the agent performs.

## Capabilities in This Project

| Capability | File | Delivered in |
|-----------|------|---------------|
| Upload and profile a dataset | [upload-and-profile.md](upload-and-profile.md) | Phase 1 |
| Ask a natural-language question and get a real answer | [ask-question.md](ask-question.md) | Phase 1 (core), Phase 2 (table polish) |
| Conversation memory, clarification, and follow-up suggestions | [conversational-refinement.md](conversational-refinement.md) | Phase 1 (memory), Phase 2 (clarification + follow-ups) |
| Visualize and export | [visualize-and-export.md](visualize-and-export.md) | Phase 2 |

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
- **Business rules**
- **Success criteria** (how we test it)
