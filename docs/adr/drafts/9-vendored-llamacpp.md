# Vendored, pinned llama.cpp binary over upstream latest

## Context

First-run must be reproducible on a clean machine, and the benchmark runtime must be fixed.

## Decision

Pin a tested llama.cpp build (version + sha256 in `configs/binaries.yaml`) and host the zip
as a GitHub Release asset in this repo; download from there, not upstream.

## Alternatives considered

| Option | Why tempting | Why rejected |
|---|---|---|
| Download latest from upstream | Always current | Release can vanish; drift breaks reproducibility/benchmark |
| Commit the binary to git | Simplest "own host" | Hundreds of MB in the repo tree |

## Consequences

**Positive:** reproducible install, fixed benchmark runtime, license-clean (MIT).
**Negative:** manual bump procedure; must pick + test variants (CUDA only for now).
**Follow-ups:** deliberate bump workflow; model license checks.

## Thesis link

Deployment reproducibility; edge-device evaluation rigor.
