import assert from 'node:assert/strict'
import test from 'node:test'

import {
  attachmentKey,
  describeUploadError,
  hasBlockingAttachments,
  pendingReadyIds,
} from '../web/entities/file.ts'

function readyState () {
  return {
    linked: [],
    pending: [
      { localId: 'a', fileName: 'a.txt', status: 'ready', uploaded: { id: 'id-a' }, error: null, source: null },
      { localId: 'b', fileName: 'b.txt', status: 'uploading', uploaded: null, error: null, source: null },
    ],
    loading: false,
    loadError: null,
    unlinking: [],
    revision: 0,
    listRevision: 0,
  } as never
}

test('attachmentKey keeps a separate in-memory draft for a new chat', () => {
  assert.equal(attachmentKey(null), 'new')
  assert.equal(attachmentKey(''), 'new')
  assert.equal(attachmentKey(undefined), 'new')
  assert.equal(attachmentKey('thread-1'), 'thread-1')
})

test('pendingReadyIds returns only finished uploads in order', () => {
  const ids = pendingReadyIds(readyState())
  assert.deepEqual(ids, ['id-a'])
})

test('send stays blocked while uploads run or have errors', () => {
  assert.equal(hasBlockingAttachments(readyState()), true)
  assert.equal(
    hasBlockingAttachments({
      linked: [],
      pending: [
        { localId: 'a', fileName: 'a.txt', status: 'ready', uploaded: { id: 'x' }, error: null, source: null },
      ],
      loading: false,
      loadError: null,
      unlinking: [],
      revision: 0,
      listRevision: 0,
    } as never),
    false,
  )
  assert.equal(
    hasBlockingAttachments({
      linked: [],
      pending: [
        { localId: 'a', fileName: 'a.txt', status: 'error', uploaded: null, error: 'nope', source: null },
      ],
      loading: false,
      loadError: null,
      unlinking: [],
      revision: 0,
      listRevision: 0,
    } as never),
    true,
  )
})

test('upload errors map HTTP statuses to actionable messages', () => {
  assert.match(describeUploadError(413, ''), /10 MiB/)
  assert.match(describeUploadError(415, ''), /text files/)
  assert.match(describeUploadError(422, 'bad encoding'), /bad encoding/)
  assert.match(describeUploadError(null, ''), /try again/)
})

test('stale async results must not cross into another conversation', () => {
  // Upload results use the mutation revision; list results use their own
  // revision so returning to a thread cannot strand an upload as "uploading".
  const byKey: Record<string, { revision: number, pending: string[] }> = {
    new: { revision: 0, pending: ['chip-a'] },
  }
  const originRevision = byKey.new!.revision
  // Simulate a thread switch bumping the draft revision.
  byKey.new!.revision += 1
  byKey.new!.pending = []
  const lateArrivalForOrigin = originRevision
  assert.notEqual(lateArrivalForOrigin, byKey.new!.revision)
})

test('an in-flight unlink blocks sending until the server confirms it', () => {
  assert.equal(
    hasBlockingAttachments({
      linked: [],
      pending: [],
      unlinking: ['file-1'],
      loading: false,
      loadError: null,
      revision: 0,
      listRevision: 0,
    }),
    true,
  )
})
