import assert from 'node:assert/strict'
import test from 'node:test'

import {
  shouldReconnectStream,
  STREAM_RECONNECT_DELAYS_MS,
} from '../web/utils/reconnect.ts'

test('uses the fixed bounded reconnect schedule', () => {
  assert.deepEqual(STREAM_RECONNECT_DELAYS_MS, [500, 1000, 2000])
  assert.equal(shouldReconnectStream({ attempt: 0, hasThreadId: true }), true)
  assert.equal(shouldReconnectStream({ attempt: 2, hasThreadId: true }), true)
  assert.equal(shouldReconnectStream({ attempt: 3, hasThreadId: true }), false)
})

test('requires a known accepted thread before reconnecting', () => {
  assert.equal(shouldReconnectStream({ attempt: 0, hasThreadId: false }), false)
})

test('retries server failures but not terminal HTTP responses', () => {
  assert.equal(
    shouldReconnectStream({ attempt: 0, hasThreadId: true, httpStatus: 503 }),
    true,
  )
  for (const httpStatus of [401, 403, 404, 409, 410, 416, 422]) {
    assert.equal(
      shouldReconnectStream({ attempt: 0, hasThreadId: true, httpStatus }),
      false,
    )
  }
})
