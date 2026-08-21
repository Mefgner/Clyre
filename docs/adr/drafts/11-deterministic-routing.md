# Deterministic routing over model-facing tools

## Context

The original L1 design let the model emit one inline read-only tool call in the fast path.
Two forces broke it. First, tools are not thin functions: even web search is a multi-stage
deterministic pipeline (resolve → fetch → extract → chunk → rank → budget), and its stage
topology, prompts, and context budgets must be authored in code — not discovered by a model
at runtime. Second, Clyre runs 9B-class local models: reliable tool selection,
argumentation, and knowing-when-to-stop are exactly what they do worst. Letting users learn
a command syntax was also rejected — the interaction must stay plain conversation.

## Decision

Fast mode **is** the router. Every user message is classified by one constrained SMALL-tier
call (recent history + registry names) into plain chat or one registered capability; a
capability is a plugin with a fixed `parse → execute → synthesize` topology that always
returns a finished answer. The model never sees raw tools; selection and topology live
entirely in code committed by the plugin author. The engine is a library of pure functions
(`fan_out`, `rank_to_budget`, `fit_to_budget`), not an executor. Full contract:
`docs/plans/tool-contract.md`.

## Alternatives considered

| Option | Why tempting | Why rejected |
|---|---|---|
| Model-facing function calling (original L1) | Mainstream pattern; flexible | 9B models misroute and hallucinate arguments; double synthesis (tool + chat); no budget control at stage boundaries |
| ReAct / while-True tool loop | Expressiveness | Already rejected by ADR-1; open loop on weak models |
| Workflow engine with runtime-composable node graphs | Plugins could "set transition rules" | Topology decided at runtime drifts back toward ReAct; undecidable cost; contradicts deterministic orchestration |
| Explicit user commands (`/search …`) | Zero classification cost | Forces users to learn syntax; breaks the conversational product |

## Consequences

**Positive:** minimal decision surface (one constrained enum per message); uniform progress
UI via stage events; misroute rate becomes a measurable benchmark metric instead of a bug
class; stage-boundary snapshots enable crash recovery, citation metadata, and cheap
refinement (param diff → re-synthesize vs re-collect).
**Negative / accepted costs:** coverage limited to registered capabilities — everything
else falls back to plain chat; multi-intent queries run the recognized capability and
disclaim the rest.
**Follow-ups:** deferred plan-and-execute reuses manifests and snapshots; planner chaining
uses `answer` text as the universal interface; hot-plug registry invalidation; clarify-with-
state waits for checkpoint infrastructure.

## Thesis link

Core empirical claim — determinism beats agentic flexibility on constrained hardware:
router misroute rate + token/call/latency counts feed M10 (OpenCode/DeepSeek-Harness as
agentic baselines). Complements the retrieval ladder R1–R3 (naive vs model-written vs
multi-query) in §6.2.
