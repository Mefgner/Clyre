# Tool Contract — deterministic routing and pipelines behind one stable interface

Status: **agreed design** (consolidates the routing pivot discussion; supersedes the
inline-tool-call draft). Feeds: Phase 2 (fast mode), Phase 5 (deferred orchestrator),
Phase 6 (thesis experiments).

---

## Problem

A "read-only tool" is not a thin function. Even web search — the canonical example — is a
deterministic multi-stage pipeline: resolve query → fetch N pages → extract clean text →
chunk → keep only chunks relevant to the query → fit into a small context window. Stages run
in separate units, some fan out over lists, every boundary needs context budgeting.

The original L1 design ("the model emits one inline tool call") gave the model tool
selection freedom. That freedom is gone by decision: **the model never sees raw tools.**
Selection is done by a deterministic router; execution follows rigidly predefined pipelines.
This shrinks the model's decision surface from "pick a tool" to "classify intent" — which is
exactly what weak local models (9B floor) do reliably.

## Decision (one paragraph)

Fast mode **is** the router: every user message is classified (one constrained SMALL-tier
call) into plain chat or one registered capability. A capability = a plugin whose handler
composes raw tools via engine primitives through a fixed skeleton (`parse` → `execute` →
`synthesize`) and always returns a finished answer. The topology of stages is chosen by the
plugin author at commit time — never by the model at runtime. The engine is a library of
pure functions, not an executor: it owns no state and makes no decisions. The outer loop of
the system closes at the human: one user message = one pass through router → chat/pipeline;
the model never decides whether to continue.

## Layers

| Layer | Audience | Contents |
|---|---|---|
| **ToolManifest** | router (+ code) | `name`, `description`, `produces`, `input_schema`, `access` |
| **Handler** | plugin author | `async def run(ctx, query) -> ToolResult`; composes raw tools via engine primitives |
| **Raw tools** | handlers | pure async functions over data: `fetch_file`, `extract_text`, `chunk_text`, `embed`, `http_fetch`, … |
| **Engine** | everyone below | combinators + shared helpers (`fan_out`, `rank_to_budget`, `fit_to_budget`); stateless |

Placement: engine lives in `api/modules/engine/` (next to the future deferred
`orchestrator/`); both the chat path and any later plan path consume it. The modular
monolith makes relocation cheap if needed.

## Two categories — not a flag

| Category | What it is | Returns | Synthesized by |
|---|---|---|---|
| **Tool** (thin) | raw lookup used *by code*: `fetch_file`, `list_project_files`, `search_project` | material (chunks, listings) | caller's context |
| **Plugin** (thick) | self-contained capability: `web_search`, `summarize_files`, … | **always a finished answer** | its own `synthesize` node |

Tools are never exposed to the model — they are building blocks for handlers. Plugins are
what the router routes to. Double synthesis is impossible by construction: the spine never
re-assembles what a plugin already assembled.

## ToolManifest

| Field | Consumer | Notes |
|---|---|---|
| `name` | router, logs | registry key |
| `description` | router | the router's only classification signal besides history; one precise phrase |
| `produces` | router now, planner later | one-line output type ("list of chunks with sources", "summary text"); always present next to `description` — raises routing correctness and enables future chaining |
| `input_schema` | `parse` node only | target for constrained decoding; never shown to the router/model |
| `access` | approval policy | `R` \| `W` \| `RW`; approval applies to write operations only (declaration now, enforcement with the deferred phase) |

Token economy: the model-facing surface per capability is `name + description + produces`.

## ToolContext

The only doorway to ambient capabilities:

- `user_id` — scope isolation; handlers never accept raw ids from the client.
- `token_budget` — ceiling for material; enforced by `ctx.fit_to_budget()` (truncate
  deterministically or fail loudly, never silently drop mid-list).
- `emit(stage_event)` — progress events with uniform stage names (`parse` / `execute` /
  `synthesize`), mapped onto NDJSON `pipeline_progress` events by the chat path. One
  emission point; the frontend stepper renders any plugin without plugin-specific UI.
- `history_slice` — recent compacted turns for `parse` and `synthesize`. Parse needs it so
  extracted entities are maximally descriptive on follow-ups; synthesize needs it because a
  plugin's answer must fit the conversation.

## Thick-tool skeleton (Template Method)

```python
class ThickTool(ABC):
    manifest: ToolManifest

    async def run(self, ctx: ToolContext, query: str) -> ToolResult:
        params   = await self.parse(ctx, query)          # constrained JSON, SMALL tier
        material = await self.execute(ctx, params)       # deterministic; may call engine
        material = ctx.fit_to_budget(material)
        return await self.synthesize(ctx, query, material)   # always; answer ownership

    @abstractmethod
    async def execute(self, ctx, params) -> Material: ...
    # parse/synthesize have default prompts; override per plugin
```

Rules baked into the skeleton:

1. **`parse` is a one-shot entity extractor** — query (+ history slice + previous
   `parsed_params` as merge base) → strict JSON via constrained decoding. Missing entities
   → deterministic template listing what is needed; the next user turn re-enters as a fresh
   query. No stateful clarification loops (see Future Work).
2. **LLM touches only the edges** (`parse`, `synthesize`, both SMALL). Everything between
   is deterministic code.
3. **No LLM compaction inside `execute`.** Unknown-size outputs are handled by boundary
   normalization + selection (see Ranking), never by generation cascades.
4. **Boundary normalization**: raw-tool outputs are capped at ingestion (e.g. first N KB of
   extracted text), chunked immediately — chunk size bounds everything downstream.
5. **Capped repair hook**: validation → at most one regeneration (for extraction-style
   plugins). Never an open loop.
6. **Error lanes**: fatal errors (`ParseError`, fatal `ExecError`) → deterministic template,
   no LLM apology call; partial material (e.g. 2 of 5 pages fetched) → `synthesize`
   answers honestly over what exists and names the gaps.

## Re-entry: refinement without a "wishes" field

User feedback ("make it shorter", "wrong files") is just the next message through the front
door: router (with history) → same plugin → `parse`. No separate feedback mechanism exists.

- `parse` receives the previous run's `parsed_params` from the snapshot as merge base and
  extracts only the delta.
- Deterministic param diff decides the branch:
  - **Branch A** — only synthesize-relevant fields changed → reuse stored
    `execute_material`, re-run `synthesize` alone (fast, cheap);
  - **Branch B** — collection itself changed → full re-collect (needed when nothing was
    wrong with the answer but the approach to gathering must change).
- Fragility is bounded: worst case is a one-shot `ParseError` → reformulation template; a
  router misroute degrades gracefully to plain chat. Nothing can break mid-pipeline because
  no mid-pipeline state is required.

## Ranking and budgeting (`rank_to_budget`)

Two separable halves, neither needing a rerank model or extra memory:

1. **Scoring** — cosine between the query embedding and chunk embeddings that were already
   computed at ingestion. Multilingual ability comes from the embedding model itself.
2. **Budget fitting** — greedy top-K until the token budget is exceeded. Exact counts come
   from `/tokenize` of the target chat model at selection time (a local tokenizer pass,
   milliseconds — negligible against minute-scale pipelines).

- Persistent `ChunkVector.token_count` is **advisory only** (telemetry/logs): it was
  computed with the embedder's tokenizer, not the consumer's.
- Tokenizer-versioned caching is **out of plan**; revisit only when optimizing
  answer-delivery latency.
- **Multi-query voting (optional booster)**: one constrained call produces 3–5 query
  reformulations → independent selections → keep chunks winning most often. Off by default;
  it is level R3 of the thesis retrieval ladder (see Thesis link).

## Citations as run metadata

No `[source:N]` markers in generated text — they would pollute context. `execute` records
touched sources deterministically in the run record; the frontend renders a disclaimer under
the answer listing the files used. Zero tokens spent inside prompts.

## Durability: L1 snapshots + background generation

Three levels were considered; L1 is chosen.

| Level | What is written | Verdict |
|---|---|---|
| L0 — nothing | only final messages persist | insufficient: a crash mid-execute loses everything |
| **L1 — stage-boundary snapshots** | one row per run: `{plugin, status, parsed_params, execute_material}` (~3 small writes/run) | **chosen** |
| L2 — full trace (dsh-style) | every prompt/token/chunk | rejected: expensive, unnecessary |

- Recovery: crash in `execute` → restart from saved params (parse skipped); crash in
  `synthesize` → re-synthesize from stored material. Cheap because `parse` is first and
  stage outputs are budget-bounded.
- The same table (`pipeline_run`) is the seed of the deferred checkpoint model
  (`agent_run`) and carries citation metadata for the UI.
- **Background generation is in scope**: generation runs as an asyncio task decoupled from
  the client connection; chunks persist to DB + replay buffer; a reconnecting client catches
  up from its last offset. Critical for non-instant (pipeline) answers.

## Router mechanics

```
input:  recent messages + user query + [{name, description, produces}] from registry
output: constrained enum: "chat" | "<plugin name>"
tier:   SMALL; runs on every message
```

- **Always LLM classification** — no slash commands, no syntax, no cheap prefilter: users
  must not learn a new interaction style.
- **Dynamic registry** — names are read from the live registry, not a hardcoded enum
  (hot-plug hook).
- **Multi-intent queries** — if any capability is recognized, it runs; the unhandled rest is
  answered with an honest disclaimer ("ask for the summary as a separate message"). True
  composition returns with the deferred planner.
- **Misroutes are a metric, not a bug** — wrong-route rate feeds benchmark M10 (the thesis
  argument for determinism). `ParseError` templates act as the safety net: a misrouted
  request fails into "reformulate", and the user self-corrects on the next turn.

## Engine primitives (grow on demand)

- `fan_out(items, unit_fn)` — parallel map over a list entity. No artificial concurrency
  limits: llama.cpp queues requests internally. Unbounded growth is prevented at the data
  boundary (normalization caps), not at the request boundary.
- `rank_to_budget(chunks, query_embedding, budget)` — see Ranking above.
- `fit_to_budget(material)` — deterministic ceiling enforcement.

Everything else already exists as pipelines (`ingest.extract_text`, `ingest.chunk_text`,
`embed.EmbeddingPipeline`, retrieval functions).

## Registration

Class-level decorator `@plugin`; the registry collects plugins at import of
`api/modules/engine/plugins/`. The router reads the registry — dynamicity gets its
mechanism here.

## Plugin zoo — the pattern applied

| Plugin | parse | execute | synthesize | Verdict |
|---|---|---|---|---|
| file capabilities (first priority) | entities: files, intent | fetch/extract/chunk/rank | answer over material | Proves the skeleton |
| `web_search` | search terms | fan-out: search → fetch → extract → chunk → rank_to_budget | answer + source list | In thesis scope; backend TBD (open question) |
| `summarize_files` | files, format | extract each → map-reduce summarization | digest | Shows nested pipelines in `execute` |
| `compare_documents` | files, aspect | extract both → section comparison | comparison output | Wants structured `produces` |
| `find_in_project` (RAG as tool) | question → embedding | vector search → hydrate chunks | answer | M7 RAG becomes just another plugin |
| `data_extract` | target schema | extract → validate (capped repair) | JSON or explicit failure | Repair-hook use case |
| `thread_digest` | period, threads | needs chat-history indexing (absent) | digest | Later / likely out of scope |

## Non-goals

- No dynamic node graph, no runtime transition rules decided by model or config.
- No YAML pipeline definitions; topologies live in code.
- Nodes never communicate except through returned values; no execution state in the engine.
- No model-visible tools, no function calling, no clarification dialogs in fast mode.

## Future work (deferred, post-thesis)

- **Plan-and-execute (M8/M9)** — planner on BIG builds finite step lists; approval gates
  enforce `access: W`. The contract above is designed so this slots in without rework:
  manifests, snapshots, and `$stepN`-style refs carry over.
- **Planner chaining** — BIG links pipeline outputs to inputs using `answer` text as the
  universal interface (`produces` guides wiring).
- **Hot-plug, two levels**: (1) lifecycle events (`plugin_mounted`/`unmounted`) invalidate
  the router's registry view — install capabilities without restart; (2) BIG composes
  pipelines from registered manifests. Inspired by DeepSeek Harness/Cordis; cited as related
  work, not imported — "everything is a plugin" contradicts ADR-1.
- **Clarify-with-state** — suspend/resume clarification dialogs land together with the
  checkpoint infrastructure they require.
- **BIG tier** — configuration stays in env/code; processes are not launched until this
  phase finds it a use (or it is removed quickly).

## Open questions

- Web-collection backend for `web_search` (SearxNG was a candidate, not committed) — decide
  when the applied tool work starts.

## Thesis link

- Retrieval quality ladder on a fixed corpus: **R1** naive user query vs **R2**
  model-written query (the `parse` node's reformulation — free, it already extracts
  entities) vs **R3** multi-query voting. Recall/precision metrics; all three levels are
  switches on one ranking path.
- Together with "passive top-k RAG vs agentic fetch" this forms the evaluation axis:
  query-processing quality × context-delivery strategy.
- Router misroute rate + token/call/latency counts feed the M10 agentic-vs-deterministic
  benchmark.

## PLAN.md integration

- New **2.6** (fast-mode routing) references this document; old inline-tool-call items
  removed; background generation added as **2.7**.
- **M5** reworded to the router model; **M8/M9** marked deferred.
- Phase 5 header notes deferral; BIG-tier note added.
- §6.2 gains the R1–R3 experiment.
