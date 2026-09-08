# Owner decisions backlog

These items were intentionally not auto-fixed during the August technical-debt cleanup because they change product behavior, public contracts, deployment policy, or model/runtime semantics. They need an explicit owner decision before implementation.

## 1. Upload limits

Choose the maximum accepted upload size and whether limits vary by file type or deployment shape. The backend currently reads the whole upload into memory before processing.

Decision needed:
- maximum file size
- whether to reject by declared `Content-Type`, extension, or both
- whether desktop and team-server limits differ

## 2. Recovery policy for files stuck in `index_status="pending"`

A crash after linking a file to a project can leave indexing permanently pending.

Decision needed:
- mark stale pending jobs failed after a timeout
- automatically retry stale jobs
- resume from a durable queue/journal
- how old a pending job must be before recovery starts

## 3. Generation terminal error wire contract

Failed generation runs are not represented strongly enough on the client wire contract.

Decision needed:
- add an explicit NDJSON `error` event
- encode terminal status in the final event
- expose failure through a separate status endpoint
- what partial assistant content should remain visible/persisted after failure

## 4. Model capability metadata

Thinking support is currently inferred from model-name substrings such as `qwen3`.

Decision needed:
- capability metadata in `configs/models.yaml`
- a separate model-family registry
- runtime discovery from llama.cpp `/props`
- precedence between catalog metadata and server discovery

Candidate metadata includes `family`, `supports_thinking`, `reasoning_format`, and chat-template kwargs.

## 5. Canonical embedding model / fingerprint

Desktop and Docker delivery shapes can use different repos/quants while presenting the same model alias. This risks mixing incompatible embedding spaces.

Decision needed:
- choose one canonical embedding artifact for all delivery shapes, or
- expand the vector-space fingerprint to include repo/file/quant identity

## 6. HTTP reconnect / generation re-attach API

The generation service supports buffered offsets internally, but the public HTTP API cannot currently re-attach to an active run after disconnect.

Decision needed:
- dedicated attach endpoint vs extending `/api/chat/stream`
- run identifier exposed to the client
- offset ownership/validation semantics
- behavior when the requested buffer was already evicted

## 7. Login rate-limit policy

Rate limiting is relevant for team-server deployment but is a product/deployment policy, not a pure bug fix.

Decision needed:
- attempts per window
- keying by IP, email, account, or a combination
- trusted proxy/header policy
- desktop/localhost exemption

## 8. Refresh-cookie security policy

`Secure` / `SameSite` behavior depends on whether Clyre is localhost-only, LAN HTTP, or HTTPS team-server deployment.

Decision needed:
- supported deployment origins
- HTTPS requirement for team server
- `SameSite` value
- whether cookie settings are environment-specific

## 9. Generation length / thinking budget

Qwen-family models can consume most of a generation budget in reasoning and return little or no visible content.

Decision needed:
- default `max_tokens`
- whether thinking gets a separate budget
- behavior for thinking-only / empty-content completion
- whether fast/constrained worker calls enforce stricter limits than user-facing chat

## 10. File deletion crash consistency

Current deletion spans two storage systems: vector/DB state and the raw file store. A DB rollback cannot restore an already deleted blob.

Decision needed:
- simple best-effort deletion
- rename/move blob to a temporary tombstone until DB commit succeeds
- durable deletion journal / outbox
- acceptable recovery behavior after process crash between storage operations

The upload path already has an in-process compensating delete; deletion needs an explicit cross-resource consistency policy rather than another implicit ordering choice.
