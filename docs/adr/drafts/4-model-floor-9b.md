# 9B parameter floor for the local model

- **Status:** accepted
- **Opened:** 2026-08-17
- **Accepted:** 2026-09-08
- **Owner:** project owner

## Context

The app must follow structured output reliably (plans, tool calls, constrained decoding).
Empirically, smaller models fail at this.

## Decision

Hard floor of 9B params (Qwen3.x-9B, Q4_K_M) for production chat and structured-output
evaluation. The smaller `role:test` model is an explicit test-infrastructure exception,
not a supported production configuration. 4GB/6GB production inference profiles are
dropped as unsupported.

## Alternatives considered

| Option | Why tempting | Why rejected |
|---|---|---|
| 4B/6B models | Fit in smaller VRAM, faster | Can't reliably follow structured output / tool calls |
| Larger than 9B | Better quality | Exceeds the 8GB consumer-GPU budget |

## Consequences

**Positive:** reliable structured output within ~6GB VRAM.
**Negative:** excludes low-VRAM hardware.
**Follow-ups:** 4B vs 9B benchmark (6.2) to demonstrate the floor.

## Thesis link

Empirical claim — "9B is the floor for tool-capable local models".
