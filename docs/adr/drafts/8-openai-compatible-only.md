# OpenAI-compatible inference layer over LiteLLM

- **Status:** accepted
- **Opened:** 2026-08-17
- **Accepted:** 2026-09-08
- **Owner:** project owner

## Context

Inference goes through llama.cpp's OpenAI-compatible `/v1/chat/completions`. The question
was whether to add a provider abstraction (LiteLLM).

## Decision

Consciously limit to the OpenAI-compatible layer only. One chat client and one embedding
client target their configured endpoints. All cognitive roles share the chat model as
defined by ADR-12. No LiteLLM.

## Alternatives considered

| Option | Why tempting | Why rejected |
|---|---|---|
| LiteLLM provider layer | Many backends for free | We are local-only; the URL is already the abstraction; added dependency |
| Direct vendor SDKs | Fine-grained control | Binds to one vendor; breaks the "any OpenAI-compatible backend" story |

## Consequences

**Positive:** minimal dependency, still portable across llama.cpp/Ollama/vLLM.
**Negative:** no cloud/weird-provider support (out of scope anyway).
**Follow-ups:** chat and embedding endpoints via env; logical call profiles only when roles
need different generation parameters.

## Thesis link

Local inference deployment analysis.
