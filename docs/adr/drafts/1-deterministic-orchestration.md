# Deterministic orchestration over ReAct agent loops

## Context

Clyre targets local LLMs (9B floor) on consumer hardware. Small models struggle to
reliably choose tools, decide when to search, re-plan, and stop — the decision surface
of a ReAct loop is exactly what they do worst. The thesis must demonstrate that shifting
orchestration into ordinary code is a measurable win on constrained hardware.

## Decision

Ordinary code owns the workflow; the LLM reasons only at the edges (planner +
synthesizer). Execution is a finite, linear Plan-and-Execute sequence — never an
open-ended ReAct loop. A step = one tool call; the engine resolves `$stepN` refs; a
verify failure triggers at most one capped re-plan.

## Alternatives considered

| Option | Why tempting | Why rejected |
|---|---|---|
| ReAct / while-True tool loop | Simplest to build, matches mainstream agent demos | Unreliable on 9B, runaway token/latency cost, non-deterministic |
| DAG / parallel sub-agents | More expressive | State machine the model can't drive reliably; one llama-server = linear only |

## Consequences

**Positive:** predictability, small decision surface, works on weak models, measurable (calls/tokens/latency).
**Negative / accepted costs:** can't handle truly open-ended tasks; caps expressiveness.
**Follow-ups:** benchmark (agentic vs deterministic), planner/synthesizer role split.

## Thesis link

Core empirical claim — "the weaker the model, the more value deterministic orchestration adds".
