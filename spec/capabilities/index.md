# Capabilities Index

## Capabilities in This Project

| Capability | File | Phase |
|-----------|------|-------|
| CSV Ingest | [csv_ingest.md](csv_ingest.md) | Phase 1 |
| NL Query | [nl_query.md](nl_query.md) | Phase 1 (text + table), Phase 2 (+ charts), Phase 3 (+ multi-file) |

## What Is a Capability?

A capability is a single, discrete action or behavior the agent performs.

## How to Add a New Capability

Run `/zero-shot-build [description]` on the existing spec. The spec-writer sub-agent will:
1. Create a new file in this directory (`<name>.md`, no number prefix)
2. Update this index
3. Flag any dependencies on existing capabilities
4. Self-review that it fits the architecture and data model before returning
