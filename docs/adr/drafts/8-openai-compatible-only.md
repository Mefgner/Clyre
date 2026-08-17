# OpenAI-compatible inference layer over LiteLLM

## Context

Inference goes through llama.cpp's OpenAI-compatible `/v1/chat/completions`. The question
was whether to add a provider abstraction (LiteLLM).

## Decision

Consciously limit to the OpenAI-compatible layer only. One client class, configured per
tier (SMALL / BIG / EMBEDDING). No LiteLLM.

## Alternatives considered

| Option | Why tempting | Why rejected |
|---|---|---|
| LiteLLM provider layer | Many backends for free | We are local-only; the URL is already the abstraction; added dependency |
| Direct vendor SDKs | Fine-grained control | Binds to one vendor; breaks the "any OpenAI-compatible backend" story |

## Consequences

**Positive:** minimal dependency, still portable across llama.cpp/Ollama/vLLM.
**Negative:** no cloud/weird-provider support (out of scope anyway).
**Follow-ups:** role-based endpoints via env.

## Thesis link

Local inference deployment analysis.
