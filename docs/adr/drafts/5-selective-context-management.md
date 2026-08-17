# Selective context management over passive global RAG

## Context

The thesis requires RAG, but for the product RAG is arguably optional — a household has no
"knowledge base", it has files tied to the work at hand, and a global KB degrades into a
dump quickly. Naive top-k injection into every prompt also damages small models (missed
chunks, noisy context).

## Decision

Explicit context injection + structured scopes (user facts, project memory, chat memory).
Semantic RAG is one mechanism among several, used only at the **project level** (a
per-project index identified by `project_id`, no global index) behind
`VectorRepository`. Injected context goes at a stable position, never mid-history.

## Alternatives considered

| Option | Why tempting | Why rejected |
|---|---|---|
| Global passive top-k RAG | Standard, easy to demo | Noise + missed chunks; degrades weak models; not scoped |
| Shared/global index | One corpus for everyone | Degrades into a dump fast; a household has no "knowledge base" |
| Embed everything | One unified mechanism | Overkill; file scope needs whole files, not chunks |

## Consequences

**Positive:** scoped, controllable context; RAG kept only where whole-file injection stops scaling (a project with dozens of large files); the corpus is bounded — deleting a project purges its index.
**Negative:** more moving parts than "always RAG".
**Follow-ups:** benchmark passive top-k vs agentic fetch (6.2).

## Thesis link

Hybrid context management — the RAG chapter's contrast.
