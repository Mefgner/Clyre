# Blocking startup embedding migration over zero-downtime

## Context

The embedder changes during the project's life. Dimension is fixed at CREATE on both
backends, so a model change = DROP + CREATE + full re-embed, which requires a live
embedding server.

## Decision

Block startup until migration completes: compare the embedder fingerprint (model + dim)
against `VectorIndexMeta`; on mismatch, recreate the store and re-ingest every project
file (idempotent, per-file commit). The app only comes up with a ready index.

## Alternatives considered

| Option | Why tempting | Why rejected |
|---|---|---|
| Zero-downtime background migration | Search stays available | State machine + coverage reporting; overkill for household scale |
| Ignore dimension mismatch | Nothing to build | Silent recall corruption |

## Consequences

**Positive:** no intermediate state; dead simple.
**Negative:** app unavailable for the migration window (minutes); needs a failure escape hatch so a broken rebuild doesn't loop startup.
**Follow-ups:** fingerprint, `recreate_schema`, console progress.

## Thesis link

"Model change is a first-class operation" — deployment/analysis chapter.
