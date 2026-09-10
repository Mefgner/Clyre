export const STREAM_RECONNECT_DELAYS_MS = [500, 1000, 2000] as const

interface ReconnectDecision {
  attempt: number
  hasThreadId: boolean
  httpStatus?: number
}

export function shouldReconnectStream ({
  attempt,
  hasThreadId,
  httpStatus,
}: ReconnectDecision): boolean {
  if (!hasThreadId || attempt >= STREAM_RECONNECT_DELAYS_MS.length) {
    return false
  }
  return httpStatus === undefined || httpStatus >= 500
}
