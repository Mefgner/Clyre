# OpenCode as benchmark baseline, not foundation

## Context

OpenCode is a mature agentic harness. The question was whether to build Clyre on top of
it or beside it.

## Decision

Build Clyre on its own deterministic runtime. Use OpenCode only as the agentic baseline
in the benchmark — same model, same queries, compare.

## Alternatives considered

| Option | Why tempting | Why rejected |
|---|---|---|
| Build on OpenCode | Free agent harness, MCP, tools | Inherits agentic assumptions we'd then strip; fights the deterministic thesis |
| Build everything from scratch, ignore OpenCode | Cleanest scope | Loses a ready-made, credible comparison point for the thesis |

## Consequences

**Positive:** honest A/B baseline; clean separation of the two approaches.
**Negative:** must maintain a fair, reproducible harness around OpenCode for the benchmark.
**Follow-ups:** M10 benchmark; fixed query set; identical model + hardware.

## Thesis link

"Evaluating the benefits of agent-based approaches" — the comparison chapter.
