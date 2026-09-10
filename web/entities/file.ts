export interface FileResponse {
  id: string
  name: string
  contentType: string
  headValue: string | null
  creationDate: string | null
  projectId: string | null
  indexStatus: string
  indexError: string | null
}

export type PendingAttachmentStatus = 'uploading' | 'ready' | 'error'

export interface PendingAttachment {
  localId: string
  fileName: string
  status: PendingAttachmentStatus
  uploaded: FileResponse | null
  error: string | null
  source: File | null
}

export interface ThreadAttachmentState {
  linked: FileResponse[]
  pending: PendingAttachment[]
  /** File ids whose detach request is still in flight. */
  unlinking: string[]
  loading: boolean
  loadError: string | null
  /** Bumped by local mutations (reset, draft adoption): invalidates uploads. */
  revision: number
  /** Bumped by each list request: invalidates only older list results, so an
   * in-flight upload survives a reload of the linked list. */
  listRevision: number
}

/** Storage key for the composer: persisted thread id, or 'new' for the draft. */
export const NEW_THREAD_DRAFT_KEY = 'new'

export function attachmentKey (threadId: string | null | undefined): string {
  return threadId || NEW_THREAD_DRAFT_KEY
}

export function pendingReadyIds (state: ThreadAttachmentState): string[] {
  return state.pending
    .filter(item => item.status === 'ready' && item.uploaded)
    .map(item => item.uploaded!.id)
}

export function hasBlockingAttachments (state: ThreadAttachmentState): boolean {
  // A detach that has not reached the server yet still counts there: sending
  // now would put the "removed" file into the next answer's context.
  if (state.unlinking.length > 0) {
    return true
  }
  return state.pending.some(item => item.status === 'uploading' || item.status === 'error')
}

/** HTTP status of an axios error, or null when the failure never left the app. */
export function httpStatus (error: unknown): number | null {
  const status = (error as { response?: { status?: unknown } })?.response?.status
  return typeof status === 'number' ? status : null
}

/** `detail` (or `detail.message`) of an axios error body, when present. */
export function httpDetail (error: unknown): string {
  const detail = (error as { response?: { data?: unknown } })?.response?.data as
    | { detail?: unknown }
    | undefined
  const value = detail?.detail
  if (typeof value === 'string') {
    return value
  }
  if (value && typeof value === 'object') {
    const message = (value as { message?: unknown }).message
    if (typeof message === 'string') {
      return message
    }
  }
  return ''
}

export function describeUploadError (status: number | null, fallback: string): string {
  if (status === 413) {
    return 'File is larger than the 10 MiB limit.'
  }
  if (status === 415) {
    return 'Only text files (.txt, .md, .csv, .json, .log, .py) are supported.'
  }
  if (status === 422) {
    return fallback || 'This file cannot be attached (encoding or format).'
  }
  if (status === 401) {
    return 'Session expired — please sign in again.'
  }
  return fallback || 'Upload failed — please try again.'
}

export function describeUnlinkError (status: number | null, fallback: string): string {
  if (status === 409) {
    return 'The file is still in use by a running answer — try again once it finishes.'
  }
  if (status === 401) {
    return 'Session expired — please sign in again.'
  }
  return fallback || 'Could not remove the file — please try again.'
}
