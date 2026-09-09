# One required chat model instead of a separate BIG tier

- **Status:** accepted
- **Opened:** 2026-09-08
- **Accepted:** 2026-09-08
- **Owner:** project owner

## Question

Should Clyre keep a separate `BIG` inference tier for planner and synthesizer, or should
one required local chat model perform every cognitive role?

## Context

Clyre targets edge devices and consumer GPUs. The default Qwen3.5-9B Q4_K_M chat model
already occupies most of an 8 GB GPU budget when its KV cache is included, while the
embedding model must remain available for project retrieval. A second, materially larger
model cannot generally reside beside them.

The `BIG` tier was introduced for the deferred Plan-and-Execute orchestrator. Today it is
optional, has no default model, and falls back to `SMALL`; the thesis-scope fast path does
not require it. Planner, router, parser, and synthesizer are cognitive roles, but roles do
not necessarily imply separate model processes.

This question affects the environment contract, downloader, desktop launcher, inference
client API, deployment documentation, hardware claims, and the thesis argument about
deterministic orchestration on constrained models.

## Decision

Require exactly one chat/reasoning model plus one embedding model. Run chat, routing,
parsing, synthesis, summarization, and any future planner on the same chat endpoint, using
logical call profiles for prompt, constrained output, thinking, temperature, context
budget, and output budget.

A second, stronger local endpoint may be reconsidered as a post-thesis extension if an
experiment demonstrates a concrete task that the baseline model cannot perform reliably.
It would not be a baseline hardware or configuration requirement.

## Alternatives considered

| Option | Why tempting | Cost or concern |
|---|---|---|
| One required chat model; logical profiles share it | Fits edge hardware, minimizes downloads and startup paths, strengthens the deterministic-runtime thesis | Planner and synthesis quality remain bounded by the 9B model |
| Keep an optional first-class `BIG_*` tier with fallback | Preserves an upgrade path for stronger local hardware | Carries configuration, launcher, downloader, tests, and documentation for a deferred feature |
| Require a separate BIG model for planner/synthesizer | Maximizes reasoning quality | Conflicts with the edge-device target and makes the baseline impractical on consumer GPUs |
| Load two chat models sequentially | Avoids simultaneous VRAM residency | Adds model-swap latency and lifecycle complexity; still increases disk and download requirements |

## Consequences

**Positive:** two required local model processes only (chat and embedding); a smaller env
contract; simpler packaging; hardware requirements match the product claim; planner
reliability becomes a direct test of deterministic orchestration rather than extra model
capacity.

**Negative / accepted costs:** users with stronger hardware do not get a dedicated model
route in the baseline architecture; future planner work may expose quality limits of 9B.

**Follow-ups:** use the single `CHAT_*` endpoint contract throughout application code,
documentation, launchers, downloader, and tests. Introduce logical inference profiles only
when two roles need demonstrably different call parameters. Decide whether an advanced
endpoint override is worthwhile after thesis evaluation.

## Deferred questions

- Whether optional multi-model routing is useful Future Work; omit it from the baseline
  until a measured need appears.
- Which call parameters belong to each logical profile; introduce profiles only with a
  concrete caller and test.

## Thesis link

This decision sharpens the core empirical claim: deterministic workflow and constrained
interfaces should make one edge-sized local model sufficient for the system's cognitive
roles.

## Discussion trail

- 2026-09-08 — owner raised the edge-device VRAM conflict and questioned the need for a
  BIG model. Discussion favored one required 9B chat model plus logical call profiles.
- 2026-09-08 — the optional BIG tier was reviewed against the edge-device baseline. No
  measured requirement supported a separate larger model.
- 2026-09-08 — owner accepted the single-model direction. `SMALL_*` was renamed directly
  to `CHAT_*`, and `BIG_*` was removed without compatibility aliases.
