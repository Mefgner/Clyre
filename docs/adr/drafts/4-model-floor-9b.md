# 9B parameter floor for the local model

## Context

The app must follow structured output reliably (plans, tool calls, constrained decoding).
Empirically, smaller models fail at this.

## Decision

Hard floor of 9B params (Qwen3.x-9B, Q4_K_M). 4GB/6GB inference profiles are dropped as
unsupported.

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
