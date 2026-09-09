# Blocking startup embedding migration over zero-downtime

- **Status:** accepted
- **Opened:** 2026-08-17
- **Accepted:** 2026-09-08
- **Owner:** project owner

## Context

The embedder changes during the project's life. Dimension is fixed at CREATE on both
backends, so a model change = DROP + CREATE + full re-embed, which requires a live
embedding server.

## Decision

Block startup while an enabled migration is actively running: compare the embedder
fingerprint (model + dim) against `VectorIndexMeta`; on mismatch, recreate the store and
re-ingest every project file (idempotent, per-file commit). A successful startup never
exposes a partially rebuilt index. If the rebuild fails, mark the index unavailable and
start the L0 chat path in degraded mode; project search returns a controlled 409 instead
of trapping the application in a startup loop.

## Alternatives considered

| Option | Why tempting | Why rejected |
|---|---|---|
| Zero-downtime background migration | Search stays available | State machine + coverage reporting; overkill for household scale |
| Ignore dimension mismatch | Nothing to build | Silent recall corruption |

## Consequences

**Positive:** no intermediate searchable state; the migration path remains simple.
**Negative:** app unavailable during a healthy migration window (minutes); after a failed
rebuild, chat remains available but project retrieval does not.
**Follow-ups:** fingerprint, `recreate_schema`, console progress.

## Thesis link

"Model change is a first-class operation" — deployment/analysis chapter.
