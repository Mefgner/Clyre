# RAG query rephrasing node over raw-prompt embedding

## Context

Embedding the raw user prompt for vector search is noisy — the prompt is a dialogue turn,
not a retrieval query. A dedicated node can reformulate/expand it for the vector store.

## Decision

A query node reformulates the prompt into a retrieval-oriented query before embedding.
In the benchmark this is compared against passive top-k with the raw prompt (agentic fetch
vs naive search).

## Alternatives considered

| Option | Why tempting | Why rejected |
|---|---|---|
| Embed the raw prompt directly | Zero extra LLM call | Poor recall — a dialogue turn is not a search query |
| Skip RAG entirely | Simplest | Thesis requires RAG; large project corpora need retrieval |

## Consequences

**Positive:** better recall per LLM call; a clean, isolated node.
**Negative:** one extra synthesis-tier call.
**Follow-ups:** 6.2 benchmark; query-quality metric.

## Thesis link

RAG effectiveness claim — query reformulation as the differentiator.
